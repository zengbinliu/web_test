const queryInput = document.getElementById("queryInput");
const sqlOutput = document.getElementById("sqlOutput");
const artifactLabel = document.getElementById("artifactLabel");
const sqlPreviewSection = document.getElementById("sqlPreviewSection");
const sqlPreviewOutput = document.getElementById("sqlPreviewOutput");
const sqlSection = document.getElementById("sqlSection");
const resultSection = document.getElementById("resultSection");
const resultMessage = document.getElementById("resultMessage");
const resultContent = document.getElementById("resultContent");
const generateBtn = document.getElementById("generateBtn");
const executeBtn = document.getElementById("executeBtn");
const confirmBtn = document.getElementById("confirmBtn");
let pendingConfirmationToken = null;


async function postJSON(path, payload) {
    const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({ success: false, message: "服务器返回了无效响应" }));
    if (!response.ok && !data.message) {
        data.message = `请求失败（HTTP ${response.status}）`;
    }
    return data;
}


function setBusy(button, busy) {
    button.disabled = busy;
    button.setAttribute("aria-busy", String(busy));
}


function showError(message) {
    resultMessage.textContent = message;
    resultMessage.className = "message error";
    resultContent.replaceChildren();
    resultSection.hidden = false;
}


function displayValue(value) {
    if (value === null || value === undefined) return "";
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
}


function appendTable(parent, columns, rows) {
    if (!rows || rows.length === 0) {
        const empty = document.createElement("p");
        empty.textContent = "没有符合条件的数据。";
        parent.appendChild(empty);
        return;
    }

    const wrapper = document.createElement("div");
    wrapper.className = "table-wrap";
    const table = document.createElement("table");
    const thead = document.createElement("thead");
    const headingRow = document.createElement("tr");
    for (const column of columns) {
        const th = document.createElement("th");
        th.scope = "col";
        th.textContent = column;
        headingRow.appendChild(th);
    }
    thead.appendChild(headingRow);

    const tbody = document.createElement("tbody");
    for (const row of rows) {
        const tr = document.createElement("tr");
        for (const column of columns) {
            const td = document.createElement("td");
            td.textContent = displayValue(row[column]);
            tr.appendChild(td);
        }
        tbody.appendChild(tr);
    }
    table.append(thead, tbody);
    wrapper.appendChild(table);
    parent.appendChild(wrapper);
}


function appendSummary(parent, text) {
    const paragraph = document.createElement("p");
    paragraph.className = "summary";
    paragraph.textContent = text;
    parent.appendChild(paragraph);
}


function renderSingleResult(result, parent) {
    switch (result.type) {
        case "select":
            appendSummary(parent, `查询返回 ${result.rows.length} 行。`);
            appendTable(parent, result.columns, result.rows);
            break;
        case "insert_preview": {
            const prefix = result.auto_created_dependency ? "自动补齐依赖：" : "";
            appendSummary(parent, `${prefix}即将执行 INSERT，预计插入 ${result.affected_rows} 行。`);
            const pre = document.createElement("pre");
            pre.className = "sql-preview";
            pre.textContent = result.sql;
            parent.appendChild(pre);
            break;
        }
        case "write_preview":
            appendSummary(parent, `即将执行 ${result.operation}，预计影响 ${result.affected_rows} 行。`);
            appendTable(parent, result.preview_columns, result.preview_rows);
            break;
        case "write_executed":
            appendSummary(parent, `${result.operation || "写操作"} 执行成功，影响 ${result.rows_affected} 行。`);
            break;
        case "data_plan_preview": {
            appendSummary(parent, `计划分 ${result.entity_count} 层，共写入 ${result.total_rows} 行。`);
            const semanticLabels = {
                email: "邮箱",
                password_hash: "密码哈希",
                password: "密码",
                salt: "盐值",
                phone: "电话",
                url: "URL",
                ip_address: "IP",
                money: "金额/价格",
                quantity: "数量",
                material: "材料",
                snapshot: "快照",
                sequence: "行号/顺序",
                code: "编码",
                name: "名称",
            };
            const rows = result.entities.map((entity) => ({
                层级: entity.id,
                数据表: entity.table,
                生成数量: entity.rows,
                上级: entity.parent || "根层级",
                每个上级生成: entity.count_per_parent || "-",
                数量规则: entity.count_mode === "at_least" ? "至少" : "精确",
                系统推断字段: (entity.inferred_fields || [])
                    .map((field) => `${field.column}（${semanticLabels[field.semantic] || field.semantic}）`)
                    .join("、") || "-",
            }));
            appendTable(
                parent,
                ["层级", "数据表", "生成数量", "上级", "每个上级生成", "数量规则", "系统推断字段"],
                rows,
            );
            break;
        }
        case "data_plan_execution": {
            appendSummary(parent, `事务执行成功，共插入 ${result.total_rows} 行。`);
            const rows = result.entities.map((entity) => ({
                层级: entity.id,
                数据表: entity.table,
                已插入: entity.rows_inserted,
            }));
            appendTable(parent, ["层级", "数据表", "已插入"], rows);
            break;
        }
        default: {
            const pre = document.createElement("pre");
            pre.className = "sql-preview";
            pre.textContent = JSON.stringify(result, null, 2);
            parent.appendChild(pre);
        }
    }
}


function renderResult(result) {
    resultContent.replaceChildren();
    if (result.dependency_rows_added) {
        appendSummary(
            resultContent,
            `系统发现并补齐了 ${result.dependency_rows_added} 条缺失的父表记录。`,
        );
    }
    if (result.inferred_values_added) {
        appendSummary(
            resultContent,
            `系统根据字段语义生成了 ${result.inferred_values_added} 个缺省值。`,
        );
    }
    if (result.type !== "batch_preview" && result.type !== "batch_execution") {
        renderSingleResult(result, resultContent);
        return;
    }

    appendSummary(resultContent, `共 ${result.statements_count} 条语句。`);
    result.results.forEach((item, index) => {
        const container = document.createElement("div");
        container.className = "batch-item";
        const title = document.createElement("h3");
        title.className = "batch-title";
        title.textContent = `第 ${index + 1} 条`;
        container.appendChild(title);
        renderSingleResult(item, container);
        resultContent.appendChild(container);
    });
}


async function generateSQL() {
    const query = queryInput.value.trim();
    if (!query) {
        showError("请输入数据需求。");
        queryInput.focus();
        return;
    }

    setBusy(generateBtn, true);
    pendingConfirmationToken = null;
    confirmBtn.hidden = true;
    try {
        const data = await postJSON("/generate", { natural_language: query });
        if (!data.success) {
            showError(data.message);
            return;
        }
        sqlOutput.value = data.data.sql;
        artifactLabel.textContent = data.data.artifact_type === "data_plan"
            ? "生成的分层数据计划"
            : "生成的 SQL";
        sqlPreviewOutput.value = data.data.sql_preview || "";
        sqlPreviewSection.hidden = !data.data.sql_preview;
        sqlSection.hidden = false;
        resultSection.hidden = true;
        sqlOutput.focus();
    } catch (error) {
        showError(`生成失败：${error.message}`);
    } finally {
        setBusy(generateBtn, false);
    }
}


async function executeSQL(confirm) {
    const sql = sqlOutput.value.trim();
    if (!sql) {
        showError("SQL 不能为空。");
        return;
    }

    const activeButton = confirm ? confirmBtn : executeBtn;
    setBusy(activeButton, true);
    try {
        const data = await postJSON("/execute", {
            sql,
            confirm,
            confirmation_token: confirm ? pendingConfirmationToken : null,
        });
        if (!data.success) {
            pendingConfirmationToken = null;
            confirmBtn.hidden = true;
            showError(data.message);
            return;
        }

        resultMessage.textContent = data.message;
        resultMessage.className = "message";
        renderResult(data.data);
        const plannedArtifact = data.data.planned_artifact || data.data.planned_sql;
        if (data.requires_confirmation && plannedArtifact) {
            sqlOutput.value = plannedArtifact;
        }
        if (data.data.sql_preview) {
            sqlPreviewOutput.value = data.data.sql_preview;
            sqlPreviewSection.hidden = false;
        }
        pendingConfirmationToken = data.requires_confirmation
            ? data.data.confirmation_token
            : null;
        confirmBtn.hidden = !data.requires_confirmation;
        resultSection.hidden = false;
    } catch (error) {
        showError(`执行失败：${error.message}`);
    } finally {
        setBusy(activeButton, false);
    }
}


generateBtn.addEventListener("click", generateSQL);
executeBtn.addEventListener("click", () => executeSQL(false));
confirmBtn.addEventListener("click", () => executeSQL(true));
sqlOutput.addEventListener("input", () => {
    pendingConfirmationToken = null;
    confirmBtn.hidden = true;
});

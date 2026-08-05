const queryInput = document.getElementById("queryInput");
const sqlOutput = document.getElementById("sqlOutput");
const artifactLabel = document.getElementById("artifactLabel");
const artifactMeta = document.getElementById("artifactMeta");
const artifactView = document.getElementById("artifactView");
const artifactViewBtn = document.getElementById("artifactViewBtn");
const artifactEditBtn = document.getElementById("artifactEditBtn");
const artifactCopyBtn = document.getElementById("artifactCopyBtn");
const sqlPreviewSection = document.getElementById("sqlPreviewSection");
const sqlPreviewOutput = document.getElementById("sqlPreviewOutput");
const sqlPreviewView = document.getElementById("sqlPreviewView");
const sqlPreviewMeta = document.getElementById("sqlPreviewMeta");
const sqlPreviewCopyBtn = document.getElementById("sqlPreviewCopyBtn");
const sqlSection = document.getElementById("sqlSection");
const resultSection = document.getElementById("resultSection");
const resultMessage = document.getElementById("resultMessage");
const resultContent = document.getElementById("resultContent");
const generateBtn = document.getElementById("generateBtn");
const executeBtn = document.getElementById("executeBtn");
const confirmBtn = document.getElementById("confirmBtn");
const toastEl = document.getElementById("toast");

const SQL_KEYWORDS = new Set([
    "select", "from", "where", "and", "or", "not", "insert", "into", "values",
    "update", "set", "delete", "create", "table", "drop", "alter", "join",
    "left", "right", "inner", "outer", "on", "as", "order", "by", "group",
    "having", "limit", "offset", "union", "all", "distinct", "null", "is",
    "in", "like", "between", "exists", "case", "when", "then", "else", "end",
    "start", "transaction", "begin", "commit", "rollback", "set", "with",
]);

let pendingConfirmationToken = null;
let currentArtifactType = "sql";
let artifactMode = "view";
let toastTimer = null;


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


function showToast(message) {
    toastEl.textContent = message;
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("show"), 1600);
}


async function copyText(text) {
    if (!text) {
        showToast("没有可复制的内容");
        return;
    }
    try {
        await navigator.clipboard.writeText(text);
        showToast("已复制到剪贴板");
    } catch (_error) {
        const helper = document.createElement("textarea");
        helper.value = text;
        helper.setAttribute("readonly", "");
        helper.style.position = "fixed";
        helper.style.left = "-9999px";
        document.body.appendChild(helper);
        helper.select();
        document.execCommand("copy");
        helper.remove();
        showToast("已复制到剪贴板");
    }
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


function escapeHtml(text) {
    return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}


function tryParseJSON(text) {
    try {
        return JSON.parse(text);
    } catch (_error) {
        return null;
    }
}


function highlightJSON(text) {
    const parsed = tryParseJSON(text);
    const pretty = parsed === null ? text : JSON.stringify(parsed, null, 2);
    const pattern = /("(?:\\.|[^"\\])*")\s*(:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g;
    let result = "";
    let lastIndex = 0;
    let match;
    while ((match = pattern.exec(pretty)) !== null) {
        result += escapeHtml(pretty.slice(lastIndex, match.index));
        const [, stringLiteral, isKey, keyword] = match;
        if (stringLiteral) {
            const cls = isKey ? "tok-key" : "tok-str";
            result += `<span class="${cls}">${escapeHtml(stringLiteral)}</span>`;
            if (isKey) result += isKey;
        } else if (keyword === "null") {
            result += `<span class="tok-null">${keyword}</span>`;
        } else if (keyword) {
            result += `<span class="tok-bool">${keyword}</span>`;
        } else {
            result += `<span class="tok-num">${escapeHtml(match[0])}</span>`;
        }
        lastIndex = pattern.lastIndex;
    }
    result += escapeHtml(pretty.slice(lastIndex));
    return result;
}


function splitSQLList(part) {
    const items = [];
    let current = "";
    let quote = null;
    let depth = 0;
    for (let i = 0; i < part.length; i += 1) {
        const ch = part[i];
        if (quote) {
            current += ch;
            if (ch === "'" && quote === "'" && part[i + 1] === "'") {
                current += part[i + 1];
                i += 1;
                continue;
            }
            if (ch === quote && part[i - 1] !== "\\") quote = null;
            continue;
        }
        if (ch === "'" || ch === '"' || ch === "`") {
            quote = ch;
            current += ch;
            continue;
        }
        if (ch === "(") {
            depth += 1;
            current += ch;
            continue;
        }
        if (ch === ")") {
            depth = Math.max(0, depth - 1);
            current += ch;
            continue;
        }
        if (ch === "," && depth === 0) {
            items.push(current.trim());
            current = "";
            continue;
        }
        current += ch;
    }
    if (current.trim()) items.push(current.trim());
    return items;
}


function readBalancedParens(text, startIndex) {
    if (text[startIndex] !== "(") return null;
    let depth = 0;
    let quote = null;
    for (let i = startIndex; i < text.length; i += 1) {
        const ch = text[i];
        if (quote) {
            if (ch === "'" && quote === "'" && text[i + 1] === "'") {
                i += 1;
                continue;
            }
            if (ch === quote && text[i - 1] !== "\\") quote = null;
            continue;
        }
        if (ch === "'" || ch === '"' || ch === "`") {
            quote = ch;
            continue;
        }
        if (ch === "(") depth += 1;
        if (ch === ")") {
            depth -= 1;
            if (depth === 0) {
                return { inner: text.slice(startIndex + 1, i), end: i + 1 };
            }
        }
    }
    return null;
}


function skipSQLTrivia(text, index) {
    let i = index;
    while (i < text.length) {
        if (/\s/.test(text[i])) {
            i += 1;
            continue;
        }
        if (text.startsWith("--", i)) {
            const newline = text.indexOf("\n", i);
            i = newline === -1 ? text.length : newline + 1;
            continue;
        }
        if (text.startsWith("/*", i)) {
            const end = text.indexOf("*/", i + 2);
            i = end === -1 ? text.length : end + 2;
            continue;
        }
        break;
    }
    return i;
}


function unwrapSQLName(name) {
    return String(name || "")
        .trim()
        .replace(/^`([^`]+)`$/, "$1")
        .replace(/^"([^"]+)"$/, "$1")
        .replace(/^'([^']+)'$/, "$1");
}


function displaySQLValue(raw) {
    const value = String(raw || "").trim();
    if (!value || /^null$/i.test(value)) {
        return { text: "NULL", kind: "null" };
    }
    if (
        (value.startsWith("'") && value.endsWith("'"))
        || (value.startsWith('"') && value.endsWith('"'))
    ) {
        const unquoted = value
            .slice(1, -1)
            .replace(/''/g, "'")
            .replace(/\\'/g, "'");
        return { text: unquoted, kind: "str" };
    }
    if (/^-?\d+(?:\.\d+)?$/.test(value)) {
        return { text: value, kind: "num" };
    }
    return { text: value, kind: "other" };
}


function parseInsertStatements(sql) {
    const text = String(sql || "");
    const inserts = [];
    const lower = text.toLowerCase();
    let cursor = 0;

    while (cursor < text.length) {
        const found = lower.indexOf("insert", cursor);
        if (found === -1) break;
        if (found > 0 && /[a-z0-9_]/i.test(text[found - 1])) {
            cursor = found + 6;
            continue;
        }

        let i = skipSQLTrivia(text, found + 6);
        if (!lower.startsWith("into", i) || /[a-z0-9_]/i.test(text[i + 4] || "")) {
            cursor = found + 6;
            continue;
        }
        i = skipSQLTrivia(text, i + 4);

        const tableMatch = text.slice(i).match(/^(?:`[^`]+`|"[^"]+"|[a-zA-Z_]\w*)(?:\s*\.\s*(?:`[^`]+`|"[^"]+"|[a-zA-Z_]\w*))?/);
        if (!tableMatch) {
            cursor = found + 6;
            continue;
        }
        const table = tableMatch[0].replace(/\s+/g, "");
        i = skipSQLTrivia(text, i + tableMatch[0].length);

        const columnsPart = readBalancedParens(text, i);
        if (!columnsPart) {
            cursor = found + 6;
            continue;
        }
        i = skipSQLTrivia(text, columnsPart.end);
        if (!lower.startsWith("values", i) || /[a-z0-9_]/i.test(text[i + 6] || "")) {
            cursor = found + 6;
            continue;
        }
        i = skipSQLTrivia(text, i + 6);

        const columns = splitSQLList(columnsPart.inner).map(unwrapSQLName);
        const rows = [];
        while (i < text.length) {
            i = skipSQLTrivia(text, i);
            const rowPart = readBalancedParens(text, i);
            if (!rowPart) break;
            rows.push(splitSQLList(rowPart.inner));
            i = skipSQLTrivia(text, rowPart.end);
            if (text[i] === ",") {
                i += 1;
                continue;
            }
            break;
        }

        if (columns.length > 0 && rows.length > 0) {
            inserts.push({ table, columns, rows });
        }
        cursor = Math.max(i, found + 6);
    }
    return inserts;
}


function groupInsertStatements(inserts) {
    const groups = [];
    const indexByKey = new Map();
    for (const insert of inserts) {
        const key = `${insert.table}|${insert.columns.join("\0")}`;
        let group = indexByKey.get(key);
        if (!group) {
            group = {
                table: insert.table,
                columns: insert.columns,
                rows: [],
            };
            indexByKey.set(key, group);
            groups.push(group);
        }
        group.rows.push(...insert.rows);
    }
    return groups;
}


function highlightSQL(sql) {
    const formatted = String(sql || "").replace(/\r\n/g, "\n");
    const pattern = /(--[^\n]*)|('(?:''|[^'])*'|`[^`]*`|"(?:\\.|[^"\\])*")|\b[a-zA-Z_][\w$]*\b|-?\d+(?:\.\d+)?/g;
    let result = "";
    let lastIndex = 0;
    let match;
    while ((match = pattern.exec(formatted)) !== null) {
        result += escapeHtml(formatted.slice(lastIndex, match.index));
        const [token, comment, quoted, word] = match;
        if (comment) {
            result += `<span class="tok-comment">${escapeHtml(comment)}</span>`;
        } else if (quoted) {
            result += `<span class="tok-str">${escapeHtml(quoted)}</span>`;
        } else if (word && SQL_KEYWORDS.has(word.toLowerCase())) {
            result += `<span class="tok-kw">${escapeHtml(word)}</span>`;
        } else if (/^-?\d/.test(token)) {
            result += `<span class="tok-num">${escapeHtml(token)}</span>`;
        } else {
            result += `<span class="tok-ident">${escapeHtml(token)}</span>`;
        }
        lastIndex = pattern.lastIndex;
    }
    result += escapeHtml(formatted.slice(lastIndex));
    return result;
}


function renderInsertGroups(groups) {
    const fragment = document.createDocumentFragment();
    for (const group of groups) {
        const block = document.createElement("section");
        block.className = "insert-block";

        const head = document.createElement("div");
        head.className = "insert-head";
        const tableName = document.createElement("span");
        tableName.className = "table-name";
        tableName.textContent = group.table;
        const rowCount = document.createElement("span");
        rowCount.className = "row-count";
        rowCount.textContent = `${group.rows.length} 行 · ${group.columns.length} 列`;
        head.append(tableName, rowCount);
        block.appendChild(head);

        const wrap = document.createElement("div");
        wrap.className = "insert-table-wrap";
        const table = document.createElement("table");
        table.className = "insert-table";

        const thead = document.createElement("thead");
        const headingRow = document.createElement("tr");
        const idxTh = document.createElement("th");
        idxTh.className = "row-idx";
        idxTh.textContent = "#";
        headingRow.appendChild(idxTh);
        for (const column of group.columns) {
            const th = document.createElement("th");
            th.textContent = column;
            th.title = column;
            headingRow.appendChild(th);
        }
        thead.appendChild(headingRow);

        const tbody = document.createElement("tbody");
        group.rows.forEach((row, rowIndex) => {
            const tr = document.createElement("tr");
            const idxTd = document.createElement("td");
            idxTd.className = "row-idx";
            idxTd.textContent = String(rowIndex + 1);
            tr.appendChild(idxTd);
            group.columns.forEach((_, columnIndex) => {
                const td = document.createElement("td");
                const displayed = displaySQLValue(row[columnIndex]);
                td.className = displayed.kind;
                td.textContent = displayed.text;
                td.title = displayed.text;
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });

        table.append(thead, tbody);
        wrap.appendChild(table);
        block.appendChild(wrap);
        fragment.appendChild(block);
    }
    return fragment;
}


function renderSQLVisual(sql) {
    const container = document.createElement("div");
    container.className = "sql-visual";
    const groups = groupInsertStatements(parseInsertStatements(sql));
    const totalRows = groups.reduce((sum, group) => sum + group.rows.length, 0);

    if (groups.length > 0) {
        container.appendChild(renderInsertGroups(groups));
    }

    const details = document.createElement("details");
    details.className = "sql-source";
    if (groups.length === 0) details.open = true;
    const summary = document.createElement("summary");
    summary.textContent = groups.length > 0 ? "查看 SQL 原文" : "SQL";
    details.appendChild(summary);
    details.appendChild(createCodePre(highlightSQL(sql)));
    container.appendChild(details);

    return {
        element: container,
        tableCount: groups.length,
        rowCount: totalRows,
    };
}


function createCodePre(html) {
    const pre = document.createElement("pre");
    pre.className = "code-block";
    pre.innerHTML = html;
    return pre;
}


function renderJSONValue(parent, value, keyName, depth = 0) {
    const li = document.createElement("li");
    const row = document.createElement("div");
    row.className = "node-row";

    const isObject = value !== null && typeof value === "object";
    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = isObject ? "toggle" : "toggle leaf";
    toggle.textContent = isObject ? "▾" : "·";
    row.appendChild(toggle);

    if (keyName !== undefined) {
        const keySpan = document.createElement("span");
        keySpan.className = "key";
        keySpan.textContent = JSON.stringify(keyName);
        row.appendChild(keySpan);
        const colon = document.createElement("span");
        colon.className = "colon";
        colon.textContent = ":";
        row.appendChild(colon);
    }

    if (!isObject) {
        const valueSpan = document.createElement("span");
        if (value === null) {
            valueSpan.className = "null";
            valueSpan.textContent = "null";
        } else if (typeof value === "string") {
            valueSpan.className = "str";
            valueSpan.textContent = JSON.stringify(value);
        } else if (typeof value === "number") {
            valueSpan.className = "num";
            valueSpan.textContent = String(value);
        } else if (typeof value === "boolean") {
            valueSpan.className = "bool";
            valueSpan.textContent = String(value);
        } else {
            valueSpan.textContent = String(value);
        }
        row.appendChild(valueSpan);
        li.appendChild(row);
        parent.appendChild(li);
        return;
    }

    const meta = document.createElement("span");
    meta.className = "meta";
    const entries = Array.isArray(value)
        ? value.map((item, index) => [index, item])
        : Object.entries(value);
    meta.textContent = Array.isArray(value)
        ? `Array(${entries.length})`
        : `Object{${entries.length}}`;
    row.appendChild(meta);
    li.appendChild(row);

    const children = document.createElement("ul");
    children.className = "children";
    const collapsedByDefault = depth >= 2 && entries.length > 0;
    if (collapsedByDefault) {
        children.classList.add("collapsed");
        toggle.textContent = "▸";
    }
    for (const [childKey, childValue] of entries) {
        renderJSONValue(children, childValue, childKey, depth + 1);
    }
    li.appendChild(children);

    toggle.addEventListener("click", () => {
        const collapsed = children.classList.toggle("collapsed");
        toggle.textContent = collapsed ? "▸" : "▾";
    });

    parent.appendChild(li);
}


function renderJSONTree(data) {
    const wrap = document.createElement("div");
    wrap.className = "json-tree";
    const root = document.createElement("ul");
    renderJSONValue(root, data, undefined, 0);
    wrap.appendChild(root);
    return wrap;
}


function countModeLabel(mode) {
    return mode === "at_least" ? "至少" : "精确";
}


function formatGeneratorSummary(generator) {
    if (!generator || typeof generator !== "object") return displayValue(generator);
    const strategy = generator.strategy || "?";
    if (strategy === "lookup") {
        const assign = generator.assign === "each" ? "逐行分配" : "固定一条";
        return `lookup ${generator.table}.${generator.column} 从第 ${generator.offset} 条（${assign}）`;
    }
    if (strategy === "prefixed_sequence") {
        return `prefixed_sequence ${generator.prefix}*`;
    }
    if (strategy === "snowflake") {
        return "snowflake";
    }
    if (strategy === "sequence") {
        return `sequence start=${generator.start} step=${generator.step}`;
    }
    return displayValue(generator);
}


function depthClass(depth) {
    if (depth <= 0) return "";
    if (depth === 1) return "child";
    return "grandchild";
}


function renderPlanSummary(plan) {
    const entities = Array.isArray(plan.entities) ? plan.entities : [];
    if (entities.length === 0) return null;

    const byId = new Map(entities.map((entity) => [entity.id, entity]));
    const childrenMap = new Map(entities.map((entity) => [entity.id, []]));
    const roots = [];
    for (const entity of entities) {
        if (entity.parent && byId.has(entity.parent)) {
            childrenMap.get(entity.parent).push(entity);
        } else {
            roots.push(entity);
        }
    }

    const container = document.createElement("div");
    container.className = "plan-summary";

    const walk = (entity, depth) => {
        const card = document.createElement("article");
        card.className = `entity-card ${depthClass(depth)}`.trim();

        const head = document.createElement("div");
        head.className = "entity-head";

        const idEl = document.createElement("span");
        idEl.className = "entity-id";
        idEl.textContent = entity.id || entity.table || "未命名层级";
        head.appendChild(idEl);

        if (entity.table) {
            const tableBadge = document.createElement("span");
            tableBadge.className = "entity-badge";
            tableBadge.textContent = entity.table;
            head.appendChild(tableBadge);
        }

        const countBadge = document.createElement("span");
        countBadge.className = "entity-badge muted";
        if (entity.parent) {
            countBadge.textContent = `${countModeLabel(entity.count_mode)} × ${entity.count_per_parent ?? "?"} / 上级`;
        } else {
            countBadge.textContent = `${countModeLabel(entity.count_mode)} × ${entity.count ?? "?"}`;
        }
        head.appendChild(countBadge);

        card.appendChild(head);

        const meta = document.createElement("div");
        meta.className = "entity-meta";
        meta.textContent = entity.parent
            ? `上级：${entity.parent}`
            : "根层级";
        card.appendChild(meta);

        const values = entity.values && typeof entity.values === "object" ? entity.values : null;
        if (values && Object.keys(values).length > 0) {
            const dl = document.createElement("dl");
            dl.className = "value-grid";
            for (const [key, value] of Object.entries(values)) {
                const dt = document.createElement("dt");
                dt.textContent = key;
                const dd = document.createElement("dd");
                dd.textContent = displayValue(value);
                dl.append(dt, dd);
            }
            card.appendChild(dl);
        }

        const generators = entity.generators && typeof entity.generators === "object"
            ? entity.generators
            : null;
        if (generators && Object.keys(generators).length > 0) {
            const dl = document.createElement("dl");
            dl.className = "value-grid";
            for (const [key, generator] of Object.entries(generators)) {
                const dt = document.createElement("dt");
                dt.textContent = `${key}（生成器）`;
                const dd = document.createElement("dd");
                dd.textContent = formatGeneratorSummary(generator);
                dl.append(dt, dd);
            }
            card.appendChild(dl);
        }

        container.appendChild(card);
        for (const child of childrenMap.get(entity.id) || []) {
            walk(child, depth + 1);
        }
    };

    for (const root of roots) walk(root, 0);
    return container;
}


function setArtifactMode(mode) {
    artifactMode = mode;
    const editing = mode === "edit";
    sqlOutput.hidden = !editing;
    artifactView.hidden = editing;
    artifactViewBtn.classList.toggle("active", !editing);
    artifactEditBtn.classList.toggle("active", editing);
    if (editing) {
        sqlOutput.focus();
    }
}


function refreshArtifactView() {
    const text = sqlOutput.value;
    artifactView.replaceChildren();

    if (!text.trim()) {
        artifactMeta.textContent = "";
        artifactView.appendChild(createCodePre(""));
        return;
    }

    if (currentArtifactType === "data_plan") {
        const parsed = tryParseJSON(text);
        if (parsed && typeof parsed === "object") {
            const entities = Array.isArray(parsed.entities) ? parsed.entities : [];
            artifactMeta.textContent = `${entities.length} 层实体`;
            const summary = renderPlanSummary(parsed);
            if (summary) artifactView.appendChild(summary);
            artifactView.appendChild(renderJSONTree(parsed));
            return;
        }
        artifactMeta.textContent = "JSON 解析失败，显示原文";
        artifactView.appendChild(createCodePre(highlightJSON(text)));
        return;
    }

    const visual = renderSQLVisual(text);
    if (visual.rowCount > 0) {
        artifactMeta.textContent = `${visual.tableCount} 张表 · ${visual.rowCount} 行`;
    } else {
        const statementCount = text.split(";").map((part) => part.trim()).filter(Boolean).length;
        artifactMeta.textContent = `${statementCount} 条语句`;
    }
    artifactView.appendChild(visual.element);
}


function refreshSqlPreviewView() {
    const text = sqlPreviewOutput.value;
    sqlPreviewView.replaceChildren();
    if (!text.trim()) {
        sqlPreviewMeta.textContent = "";
        return;
    }
    const visual = renderSQLVisual(text);
    if (visual.rowCount > 0) {
        sqlPreviewMeta.textContent = `${visual.tableCount} 张表 · ${visual.rowCount} 行（表格视图）`;
    } else {
        const statementCount = text
            .split(";")
            .map((part) => part.trim())
            .filter((part) => part && !part.startsWith("--"))
            .length;
        sqlPreviewMeta.textContent = `${statementCount} 条语句`;
    }
    sqlPreviewView.appendChild(visual.element);
}


function setArtifact(text, artifactType) {
    currentArtifactType = artifactType || (tryParseJSON(text)?.kind ? "data_plan" : "sql");
    sqlOutput.value = text || "";
    artifactLabel.textContent = currentArtifactType === "data_plan"
        ? "生成的分层数据计划"
        : "生成的 SQL";
    refreshArtifactView();
    setArtifactMode("view");
}


function setSqlPreview(text) {
    sqlPreviewOutput.value = text || "";
    const hasPreview = Boolean(text && text.trim());
    sqlPreviewSection.hidden = !hasPreview;
    if (hasPreview) refreshSqlPreviewView();
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
            parent.appendChild(renderSQLVisual(result.sql).element);
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
            pre.innerHTML = highlightJSON(JSON.stringify(result, null, 2));
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
            pendingConfirmationToken = null;
            confirmBtn.hidden = true;
            showError(data.message);
            return;
        }
        setArtifact(data.data.sql, data.data.artifact_type);
        setSqlPreview(data.data.sql_preview || "");
        sqlSection.hidden = false;
        resultSection.hidden = true;
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
            setArtifact(plannedArtifact, currentArtifactType);
        }
        if (data.data.sql_preview) {
            setSqlPreview(data.data.sql_preview);
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
artifactViewBtn.addEventListener("click", () => {
    refreshArtifactView();
    setArtifactMode("view");
});
artifactEditBtn.addEventListener("click", () => setArtifactMode("edit"));
artifactCopyBtn.addEventListener("click", () => copyText(sqlOutput.value));
sqlPreviewCopyBtn.addEventListener("click", () => copyText(sqlPreviewOutput.value));
sqlOutput.addEventListener("input", () => {
    pendingConfirmationToken = null;
    confirmBtn.hidden = true;
});

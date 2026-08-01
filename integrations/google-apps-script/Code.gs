const SHEET_NAME = "manual_submissions";
const HEADERS = [
  "created_at",
  "event_id",
  "action",
  "job_key",
  "status",
  "manual_submitted_at",
  "company",
  "title",
  "location",
  "link",
  "score",
  "requirements",
  "fit",
  "note",
  "user_agent",
];

function doGet(e) {
  const params = (e && e.parameter) || {};
  return respond_(params, route_(params));
}

function doPost(e) {
  const params = parsePostParams_(e);
  return respond_(params, route_(params));
}

function route_(params) {
  const action = stringParam_(params, "action") || "listUpdates";
  if (action === "listUpdates") {
    return statePayload_();
  }
  if (action === "markManualSubmitted") {
    return recordManualSubmitted_(params);
  }
  if (action === "clearManualSubmitted") {
    return recordClearManualSubmitted_(params);
  }
  return { ok: false, error: "unknown_action", action };
}

function recordManualSubmitted_(params) {
  const jobKey = stringParam_(params, "job_key");
  if (!jobKey) {
    return { ok: false, error: "missing_job_key" };
  }

  const submittedAt = stringParam_(params, "manual_submitted_at") || nowString_();
  const eventId = stringParam_(params, "event_id") || Utilities.getUuid();
  const duplicate = eventExists_(eventId);
  if (!duplicate) {
    appendEvent_(params, eventId, "markManualSubmitted", "הוגש ידנית", submittedAt);
    sendTelegramManualSubmitted_(params, submittedAt);
  }

  const payload = statePayload_();
  payload.duplicate = duplicate;
  return payload;
}

function recordClearManualSubmitted_(params) {
  const jobKey = stringParam_(params, "job_key");
  if (!jobKey) {
    return { ok: false, error: "missing_job_key" };
  }

  const eventId = stringParam_(params, "event_id") || Utilities.getUuid();
  const duplicate = eventExists_(eventId);
  if (!duplicate) {
    appendEvent_(params, eventId, "clearManualSubmitted", "", "");
  }

  const payload = statePayload_();
  payload.duplicate = duplicate;
  return payload;
}

function appendEvent_(params, eventId, action, status, submittedAt) {
  const sheet = getSheet_();
  sheet.appendRow([
    nowString_(),
    eventId,
    action,
    stringParam_(params, "job_key"),
    status,
    submittedAt,
    stringParam_(params, "company"),
    stringParam_(params, "title"),
    stringParam_(params, "location"),
    stringParam_(params, "link"),
    stringParam_(params, "score"),
    stringParam_(params, "requirements"),
    stringParam_(params, "fit"),
    stringParam_(params, "note"),
    stringParam_(params, "user_agent"),
  ]);
}

function statePayload_() {
  return {
    ok: true,
    generated_at: nowString_(),
    manual_submissions: buildEffectiveManualSubmissions_(),
  };
}

function buildEffectiveManualSubmissions_() {
  const sheet = getSheet_();
  const values = sheet.getDataRange().getValues();
  if (values.length <= 1) {
    return {};
  }

  const header = headerMap_(values[0]);
  const result = {};
  for (let rowIndex = 1; rowIndex < values.length; rowIndex += 1) {
    const row = values[rowIndex];
    const action = cell_(row, header, "action");
    const jobKey = cell_(row, header, "job_key");
    if (!jobKey) {
      continue;
    }
    if (action === "clearManualSubmitted") {
      delete result[jobKey];
      continue;
    }
    if (action === "markManualSubmitted") {
      result[jobKey] = {
        submittedAt: cell_(row, header, "manual_submitted_at"),
        updatedAt: cell_(row, header, "created_at"),
        note: cell_(row, header, "note"),
        source: "remote",
      };
    }
  }
  return result;
}

function eventExists_(eventId) {
  if (!eventId) {
    return false;
  }

  const sheet = getSheet_();
  const lastRow = sheet.getLastRow();
  if (lastRow <= 1) {
    return false;
  }

  const header = headerMap_(sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0]);
  const eventColumn = header.event_id;
  if (eventColumn === undefined) {
    return false;
  }

  const values = sheet.getRange(2, eventColumn + 1, lastRow - 1, 1).getValues();
  return values.some((row) => String(row[0]) === eventId);
}

function sendTelegramManualSubmitted_(params, submittedAt) {
  const properties = PropertiesService.getScriptProperties();
  const token = properties.getProperty("TELEGRAM_BOT_TOKEN");
  const chatId = properties.getProperty("TELEGRAM_CHAT_ID");
  if (!token || !chatId) {
    return { sent: false, reason: "missing_telegram_config" };
  }

  const company = stringParam_(params, "company");
  const title = stringParam_(params, "title");
  const location = stringParam_(params, "location");
  const link = stringParam_(params, "link");
  const score = stringParam_(params, "score");
  const requirements = stringParam_(params, "requirements");
  const fit = stringParam_(params, "fit");

  const text = [
    "הוגשה ידנית בדשבורד",
    `תאריך ושעה: ${submittedAt}`,
    `חברה: ${company}`,
    `משרה: ${title}`,
    `מיקום: ${location}`,
    `ציון התאמה: ${score}/100`,
    `קישור: ${link}`,
    "",
    "דרישות מרכזיות:",
    requirements || "לא נשלחו דרישות מהדשבורד",
    "",
    "סיבות התאמה:",
    fit || "לא נשלחו סיבות התאמה מהדשבורד",
    "",
    "מידע כללי על החברה:",
    `${company}${location ? " | " + location : ""}`,
  ].join("\n");

  const response = UrlFetchApp.fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
    method: "post",
    contentType: "application/json; charset=utf-8",
    payload: JSON.stringify({
      chat_id: chatId,
      text,
      disable_web_page_preview: false,
    }),
    muteHttpExceptions: true,
  });

  return {
    sent: response.getResponseCode() >= 200 && response.getResponseCode() < 300,
    status: response.getResponseCode(),
  };
}

function getSheet_() {
  const spreadsheet = getSpreadsheet_();
  let sheet = spreadsheet.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(SHEET_NAME);
  }

  if (sheet.getLastRow() === 0) {
    sheet.appendRow(HEADERS);
    sheet.setFrozenRows(1);
  } else {
    const existing = sheet.getRange(1, 1, 1, Math.max(sheet.getLastColumn(), HEADERS.length)).getValues()[0];
    const needsHeader = HEADERS.some((name, index) => existing[index] !== name);
    if (needsHeader) {
      sheet.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]);
      sheet.setFrozenRows(1);
    }
  }

  return sheet;
}

function getSpreadsheet_() {
  const id = PropertiesService.getScriptProperties().getProperty("JOB_SEARCHER_SHEET_ID");
  if (id) {
    return SpreadsheetApp.openById(id);
  }

  const active = SpreadsheetApp.getActiveSpreadsheet();
  if (!active) {
    throw new Error("Set JOB_SEARCHER_SHEET_ID in Script Properties or bind the script to a Google Sheet.");
  }
  return active;
}

function parsePostParams_(e) {
  const params = {};
  if (e && e.parameter) {
    Object.keys(e.parameter).forEach((key) => {
      params[key] = e.parameter[key];
    });
  }

  const contents = e && e.postData && e.postData.contents;
  if (!contents) {
    return params;
  }

  try {
    const parsed = JSON.parse(contents);
    Object.keys(parsed).forEach((key) => {
      params[key] = parsed[key];
    });
  } catch (error) {
    contents.split("&").forEach((pair) => {
      const parts = pair.split("=");
      if (parts[0]) {
        params[decodeURIComponent(parts[0])] = decodeURIComponent((parts[1] || "").replace(/\+/g, " "));
      }
    });
  }
  return params;
}

function respond_(params, payload) {
  const json = JSON.stringify(payload);
  const callback = stringParam_(params, "callback");
  if (callback && isSafeCallback_(callback)) {
    return ContentService.createTextOutput(`${callback}(${json});`).setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  return ContentService.createTextOutput(json).setMimeType(ContentService.MimeType.JSON);
}

function isSafeCallback_(callback) {
  return /^[A-Za-z_$][0-9A-Za-z_$]*(\.[A-Za-z_$][0-9A-Za-z_$]*)*$/.test(callback);
}

function stringParam_(params, key) {
  const value = params && params[key];
  if (Array.isArray(value)) {
    return String(value[0] || "").trim();
  }
  return String(value || "").trim();
}

function headerMap_(headerRow) {
  const map = {};
  headerRow.forEach((name, index) => {
    if (name) {
      map[String(name)] = index;
    }
  });
  return map;
}

function cell_(row, header, name) {
  const index = header[name];
  if (index === undefined) {
    return "";
  }
  const value = row[index];
  if (value instanceof Date) {
    return Utilities.formatDate(value, timezone_(), "yyyy-MM-dd HH:mm");
  }
  return String(value || "");
}

function nowString_() {
  return Utilities.formatDate(new Date(), timezone_(), "yyyy-MM-dd HH:mm");
}

function timezone_() {
  return PropertiesService.getScriptProperties().getProperty("TIMEZONE") || Session.getScriptTimeZone() || "Asia/Jerusalem";
}

/**
 * apps-script-mcp bridge.
 *
 * Paste this file into a new project at script.google.com, add the "Drive API"
 * service (Services > +), run setup() once,
 * then deploy as a web app (Execute as: Me, Who has access: Anyone).
 * The local MCP server calls the web app URL with the key that setup() prints.
 */

const BRIDGE_VERSION = '1.1.3';
const SCRIPT_MIME = 'application/vnd.google-apps.script';
const SCRIPT_JSON_MIME = 'application/vnd.google-apps.script+json';
const KEY_PROPERTY = 'BRIDGE_KEY';

/**
 * Run from the editor. Grants permissions and prints the secret key, creating
 * one on first run. Safe to run again after changing scopes; the key is kept.
 */
function setup() {
  // Google only prompts for the scopes a function uses itself, so ask for
  // every manifest scope explicitly; run_code needs all of them later.
  if (ScriptApp.requireAllScopes) ScriptApp.requireAllScopes(ScriptApp.AuthMode.FULL);
  const props = PropertiesService.getScriptProperties();
  let key = props.getProperty(KEY_PROPERTY);
  if (!key) {
    // 4 random UUIDs: 128 hex chars, ~488 bits of randomness.
    key = [1, 2, 3, 4].map(function () { return Utilities.getUuid(); }).join('').replace(/-/g, '');
    props.setProperty(KEY_PROPERTY, key);
  }
  console.log('APPS_SCRIPT_BRIDGE_KEY (keep it secret): ' + key);
}

/** Replaces the secret key. The old key stops working immediately. */
function rotateKey() {
  PropertiesService.getScriptProperties().deleteProperty(KEY_PROPERTY);
  setup();
}

function doPost(e) {
  let out;
  try {
    const req = JSON.parse(e.postData.contents);
    checkKey_(req.key);
    const handler = ACTIONS[req.action];
    if (!handler) throw new Error('Unknown action: ' + req.action);
    out = { ok: true, data: handler(req.params || {}) };
  } catch (err) {
    out = { ok: false, error: String((err && err.message) || err) };
  }
  return ContentService.createTextOutput(JSON.stringify(out)).setMimeType(
    ContentService.MimeType.JSON
  );
}

function doGet() {
  return ContentService.createTextOutput('apps-script-mcp bridge ' + BRIDGE_VERSION);
}

function checkKey_(given) {
  const expected = PropertiesService.getScriptProperties().getProperty(KEY_PROPERTY);
  if (!expected) throw new Error('Bridge has no key yet. Run setup() in the Apps Script editor.');
  given = String(given || '');
  let diff = given.length ^ expected.length;
  for (let i = 0; i < expected.length; i++) {
    diff |= expected.charCodeAt(i) ^ (given.charCodeAt(i) || 0);
  }
  if (diff !== 0) throw new Error('Invalid bridge key.');
}

const ACTIONS = {
  status: function () {
    return {
      version: BRIDGE_VERSION,
      email: Session.getEffectiveUser().getEmail(),
      bridgeScriptId: ScriptApp.getScriptId(),
      driveService: typeof Drive !== 'undefined',
    };
  },

  run_code: function (p) {
    return execute_(String(p.code || ''), []);
  },

  run_function: function (p) {
    const name = String(p.function_name || '');
    if (!/^[A-Za-z_$][\w$]*$/.test(name)) throw new Error('Invalid function name: ' + name);
    const files = getFiles_(p.script_id).filter(function (f) {
      return f.type === 'SERVER_JS';
    });
    const source = files
      .map(function (f) {
        return '// ---- ' + f.name + '.gs ----\n' + f.source;
      })
      .join('\n');
    return execute_(source + '\nreturn ' + name + '.apply(null, __args);', p.args || []);
  },

  list_projects: function (p) {
    let q = "mimeType = 'application/vnd.google-apps.script' and trashed = false";
    if (p.query) {
      q += " and title contains '" + String(p.query).replace(/\\/g, '\\\\').replace(/'/g, "\\'") + "'";
    }
    const it = DriveApp.searchFiles(q);
    const limit = Math.min(Number(p.limit) || 50, 200);
    const out = [];
    while (it.hasNext() && out.length < limit) {
      const f = it.next();
      out.push({
        scriptId: f.getId(),
        title: f.getName(),
        updated: f.getLastUpdated().toISOString(),
        url: 'https://script.google.com/d/' + f.getId() + '/edit',
      });
    }
    return out;
  },

  create_project: function (p) {
    const title = String(p.title || 'Untitled project');
    const blob = scriptBlob_([{ name: 'Code', type: 'server_js', source: 'function myFunction() {\n\n}\n' }]);
    const drive = drive_();
    const file = drive.Files.create
      ? drive.Files.create({ name: title, mimeType: SCRIPT_MIME }, blob)
      : drive.Files.insert({ title: title, mimeType: SCRIPT_MIME }, blob, { convert: true });
    return {
      scriptId: file.id,
      title: title,
      url: 'https://script.google.com/d/' + file.id + '/edit',
    };
  },

  get_project: function (p) {
    const file = DriveApp.getFileById(String(p.script_id || ''));
    return {
      scriptId: file.getId(),
      title: file.getName(),
      files: getFiles_(p.script_id).map(publicFile_),
    };
  },

  write_file: function (p) {
    const name = String(p.name || '');
    if (!name) throw new Error('File name is required.');
    const type = p.type || (name === 'appsscript' ? 'JSON' : 'SERVER_JS');
    if (['SERVER_JS', 'HTML', 'JSON'].indexOf(type) < 0) throw new Error('Invalid file type: ' + type);
    const files = getFiles_(p.script_id);
    const existing = files.filter(function (f) {
      return f.name === name;
    })[0];
    if (existing) {
      existing.type = type;
      existing.source = String(p.source);
    } else {
      files.push({ name: name, type: type, source: String(p.source) });
    }
    putFiles_(p.script_id, files);
    return { scriptId: p.script_id, name: name, type: type, created: !existing, fileCount: files.length };
  },

  delete_file: function (p) {
    const name = String(p.name || '');
    if (name === 'appsscript') throw new Error('The appsscript manifest cannot be deleted.');
    const files = getFiles_(p.script_id);
    const kept = files.filter(function (f) {
      return f.name !== name;
    });
    if (kept.length === files.length) throw new Error('No file named "' + name + '" in this project.');
    putFiles_(p.script_id, kept);
    return { scriptId: p.script_id, deleted: name, fileCount: kept.length };
  },
};

/** Runs a function body with captured logging. Never throws for user code errors. */
function execute_(body, args) {
  const logs = [];
  const write = function () {
    logs.push(Array.prototype.map.call(arguments, show_).join(' '));
  };
  const fakeConsole = { log: write, info: write, warn: write, error: write, debug: write };
  const fakeLogger = {
    log: function () {
      write.apply(null, arguments);
      return fakeLogger;
    },
    getLog: function () {
      return logs.join('\n');
    },
    clear: function () {
      logs.length = 0;
    },
  };
  try {
    const fn = new Function('console', 'Logger', '__args', body);
    const result = fn(fakeConsole, fakeLogger, args);
    return { success: true, result: serialize_(result), logs: logs };
  } catch (err) {
    return {
      success: false,
      error: String((err && err.message) || err),
      stack: (err && err.stack) || null,
      logs: logs,
    };
  }
}

function show_(v) {
  if (typeof v === 'string') return v;
  try {
    const s = JSON.stringify(v);
    return s === undefined ? String(v) : s;
  } catch (err) {
    return String(v);
  }
}

function serialize_(v) {
  if (v === undefined) return null;
  try {
    const s = JSON.stringify(v);
    return s === undefined ? String(v) : JSON.parse(s);
  } catch (err) {
    return String(v);
  }
}

/**
 * Reads a standalone script's files through the Drive export endpoint.
 * Each file keeps its internal `id`, which putFiles_ needs to update it in place.
 */
function getFiles_(scriptId) {
  if (!scriptId) throw new Error('script_id is required.');
  const url =
    'https://script.google.com/feeds/download/export?format=json&id=' +
    encodeURIComponent(String(scriptId));
  const res = UrlFetchApp.fetch(url, {
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    muteHttpExceptions: true,
  });
  const code = res.getResponseCode();
  const text = res.getContentText();
  let json = null;
  try {
    json = JSON.parse(text);
  } catch (err) {
    // handled below
  }
  if (code >= 300 || !json || !json.files) {
    throw new Error(
      'Could not read script ' + scriptId + ' (HTTP ' + code + '). ' +
        'Only standalone script projects you can access are supported, not scripts bound to a Sheet, Doc or Form.'
    );
  }
  return json.files.map(function (f) {
    return { id: f.id, name: f.name, type: String(f.type).toUpperCase(), source: f.source || '' };
  });
}

/** Replaces all files of a script. Files without an `id` are created; missing ones are deleted. */
function putFiles_(scriptId, files) {
  drive_().Files.update({}, String(scriptId), scriptBlob_(files));
}

function scriptBlob_(files) {
  const payload = files.map(function (f) {
    const out = { name: f.name, type: String(f.type).toLowerCase(), source: f.source };
    if (f.id) out.id = f.id;
    return out;
  });
  return Utilities.newBlob(JSON.stringify({ files: payload }), SCRIPT_JSON_MIME);
}

function publicFile_(f) {
  return { name: f.name, type: f.type, source: f.source };
}

function drive_() {
  if (typeof Drive === 'undefined') {
    throw new Error(
      'The Drive service is not enabled in the bridge. In the bridge editor click Services > + > ' +
        'Drive API > Add, then Deploy > Manage deployments > Edit > Version: New version.'
    );
  }
  return Drive;
}

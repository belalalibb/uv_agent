const fs = require('fs');
const path = require('path');

// Mock DOM elements that simulate flexbox layout required by WebAssembly PoW
class MockElement {
    constructor(tag) {
        this.tagName = tag.toUpperCase();
        this._id = '';
        this._innerHTML = '';
        this.style = {};
        this._children = [];
        this.attributes = {};
        this.containerWidth = 58;
        this.parent = null;
        this.isFlexChild = false;
    }
    set id(val) { this._id = val; }
    get id() { return this._id; }
    setAttribute(k, v) {
        this.attributes[k] = v;
        if (k === 'style') {
            const calcMatch = v.match(/width:\s*calc\((\d+)px\s*-\s*(\d+)px\)/i);
            if (calcMatch) {
                this.containerWidth = parseInt(calcMatch[1], 10) - parseInt(calcMatch[2], 10);
            } else {
                const emMatch = v.match(/width:\s*(\d+(?:\.\d+)?)em/i);
                const fsMatch = v.match(/font-size:\s*(\d+(?:\.\d+)?)px/i);
                if (emMatch) {
                    const em = parseFloat(emMatch[1]);
                    const fs = fsMatch ? parseFloat(fsMatch[1]) : 12;
                    this.containerWidth = em * fs;
                } else {
                    const pxMatch = v.match(/width:\s*(\d+(?:\.\d+)?)px/i);
                    if (pxMatch) {
                        this.containerWidth = parseFloat(pxMatch[1]);
                    }
                }
            }
        }
    }
    getAttribute(k) { return this.attributes[k]; }
    appendChild(child) {
        child.parent = this;
        this._children.push(child);
        return child;
    }
    removeChild(child) {
        this._children = this._children.filter(c => c !== child);
        return child;
    }
    set innerHTML(val) {
        this._innerHTML = val;
        this._children = [];
        const divMatches = val.match(/<div/gi);
        const count = divMatches ? divMatches.length : 0;
        for (let i = 0; i < count; i++) {
            const child = new MockElement('div');
            child.isFlexChild = true;
            child.parent = this;
            this._children.push(child);
        }
    }
    get innerHTML() {
        return this._innerHTML;
    }
    get children() {
        return this._children;
    }
    get clientWidth() {
        if (this.isFlexChild) {
            const parentWidth = (this.parent && this.parent.containerWidth) || 58;
            const n = (this.parent && this.parent.children.length) || 1;
            return Math.round(parentWidth / n);
        }
        return this.containerWidth || 58;
    }
}

const mockDoc = {
    createElement(tag) { return new MockElement(tag); },
    documentElement: new MockElement('HTML'),
    body: new MockElement('BODY'),
    location: { href: "https://notegpt.io/ai-agent" }
};

const mockWindow = {
    document: mockDoc,
    navigator: {
        userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
        webdriver: false
    },
    location: mockDoc.location,
    crypto: require('crypto').webcrypto,
    getComputedStyle(el) {
        return {
            getPropertyValue(prop) {
                if (prop === "width") {
                    if (el.isFlexChild) {
                        const parentWidth = (el.parent && el.parent.containerWidth) || 58;
                        const n = (el.parent && el.parent.children.length) || 1;
                        const subpixels = Math.floor((parentWidth / n) * 64);
                        const px = subpixels / 64;
                        const formatted = px % 1 === 0 ? px.toString() : parseFloat(px.toFixed(4)).toString();
                        return formatted + "px";
                    }
                    const total = el.containerWidth || 58;
                    return total + "px";
                }
                if (prop === "display") return "flex";
                if (prop === "flex") return "1";
                if (prop === "box-sizing") return "border-box";
                return "";
            }
        };
    }
};

global.window = mockWindow;
global.document = mockDoc;
global.navigator = mockWindow.navigator;
global.location = mockDoc.location;
global.self = mockWindow;

const wasmPath = path.join(__dirname, 'crypto_util.wasm');
const wasmBuffer = fs.readFileSync(wasmPath);

let b;
let y = 0;
let a = null;
let c = null;

function o() {
    return (a === null || a.buffer.detached === true || a.buffer.detached === undefined && a.buffer !== b.memory.buffer) && (a = new DataView(b.memory.buffer)), a;
}

function l() {
    return (c === null || c.byteLength === 0) && (c = new Uint8Array(b.memory.buffer)), c;
}

function r(e) {
    let t = b.__externref_table_alloc();
    return b.__wbindgen_externrefs.set(t, e), t;
}

function i(e, t) {
    return e >>>= 0, l().subarray(e / 1, e / 1 + t);
}

function s(e, t) {
    return e >>>= 0, _(e, t);
}

function u(e, t) {
    try {
        return e.apply(this, t);
    } catch (e) {
        let t = r(e);
        b.__wbindgen_exn_store(t);
    }
}

function d(e) { return e == null; }

var v = new TextEncoder();
function f(e, t, n) {
    if (n === undefined) {
        let n = v.encode(e), r = t(n.length, 1) >>> 0;
        return l().subarray(r, r + n.length).set(n), y = n.length, r;
    }
    let r = e.length, i = t(r, 1) >>> 0, a = l(), o = 0;
    for (; o < r; o++) {
        let t = e.charCodeAt(o);
        if (t > 127) break;
        a[i + o] = t;
    }
    if (o !== r) {
        o !== 0 && (e = e.slice(o)), i = n(i, r, r = o + e.length * 3, 1) >>> 0;
        let t = l().subarray(i + o, i + r), a = v.encodeInto(e, t);
        o += a.written, i = n(i, r, o, 1) >>> 0;
    }
    return y = o, i;
}

function p(e) {
    let t = b.__wbindgen_externrefs.get(e);
    return b.__externref_table_dealloc(e), t;
}

var m = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true });
m.decode();
var h = 2146435072, g = 0;
function _(e, t) {
    return g += t, g >= h && (m = new TextDecoder('utf-8', { ignoreBOM: true, fatal: true }), m.decode(), g = t), m.decode(l().subarray(e, e + t));
}

const imports = {
    __proto__: null,
    "./crypto_util_bg.js": {
        __proto__: null,
        __wbg___wbindgen_is_falsy_f8005c4864e74c90: function(e) { return !e; },
        __wbg___wbindgen_is_function_d4c2480b46f29e33: function(e) { return typeof e == 'function'; },
        __wbg___wbindgen_is_object_e04e3a51a90cde43: function(e) { return typeof e == 'object' && !!e; },
        __wbg___wbindgen_is_string_3db04af369717583: function(e) { return typeof e == 'string'; },
        __wbg___wbindgen_is_undefined_5957b329897cc39c: function(e) { return e === undefined; },
        __wbg___wbindgen_throw_bd5a70920abf0236: function(e, t) { throw Error(s(e, t)); },
        __wbg_appendChild_023bbb6d63210eba: function() { return u(function(e, t) { return e.appendChild(t); }, arguments); },
        __wbg_body_36314a75ae5381db: function(e) { let t = e.body; return d(t) ? 0 : r(t); },
        __wbg_call_1aea13500fe8ff6c: function() { return u(function(e, t, n) { return e.call(t, n); }, arguments); },
        __wbg_children_9fc528ade3ea173f: function(e) { return e.children; },
        __wbg_clientWidth_8043da2fcb723102: function(e) { return e.clientWidth; },
        __wbg_createElement_22af76933a7b7e81: function() { return u(function(e, t, n) { return e.createElement(s(t, n)); }, arguments); },
        __wbg_crypto_38df2bab126b63dc: function(e) { return e.crypto; },
        __wbg_documentElement_f146626e6bc2f644: function(e) { let t = e.documentElement; return d(t) ? 0 : r(t); },
        __wbg_document_8d00b6db6f4e3e5e: function(e) { let t = e.document; return d(t) ? 0 : r(t); },
        __wbg_getComputedStyle_54985c5cd0d50b68: function() {
            return u(function(e, t) {
                let n = e.getComputedStyle(t);
                return d(n) ? 0 : r(n);
            }, arguments);
        },
        __wbg_getHours_defd69626029ce3f: function(e) { return e.getHours(); },
        __wbg_getPropertyValue_60177298ed778c76: function() {
            return u(function(e, t, n, r) {
                let propName = s(n, r);
                let val = t.getPropertyValue(propName);
                let i = f(val, b.__wbindgen_malloc, b.__wbindgen_realloc);
                let a = y;
                o().setInt32(e + 4, a, true);
                o().setInt32(e + 0, i, true);
            }, arguments);
        },
        __wbg_getRandomValues_c44a50d8cfdaebeb: function() { return u(function(e, t) { e.getRandomValues(t); }, arguments); },
        __wbg_get_d8a3d51a73d14c8a: function() { return u(function(e, t) { return Reflect.get(e, t); }, arguments); },
        __wbg_has_509eb022105825c9: function() { return u(function(e, t) { return Reflect.has(e, t); }, arguments); },
        __wbg_href_42d0a7d79a5a0fe5: function() { return u(function(e, t) { let n = t.href, r = f(n, b.__wbindgen_malloc, b.__wbindgen_realloc), i = y; o().setInt32(e + 4, i, true); o().setInt32(e + 0, r, true); }, arguments); },
        __wbg_instanceof_HtmlElement_51b34b7de7e6e993: function(e) { return true; },
        __wbg_instanceof_Window_4bfad3a9470c25c9: function(e) { return true; },
        __wbg_item_4ab2528204fdf759: function(e, t) { let n = e.item ? e.item(t >>> 0) : e[t >>> 0]; return d(n) ? 0 : r(n); },
        __wbg_length_090b6aa6235450ba: function(e) { return e.length; },
        __wbg_location_bb43558c9f37b0ca: function(e) { return e.location; },
        __wbg_msCrypto_bd5a034af96bcba6: function(e) { return 0; },
        __wbg_navigator_cda717510f3a4a47: function(e) { return e.navigator; },
        __wbg_new_0_1211b165db93342c: function() { return new Date(); },
        __wbg_new_ebde992a0bf6bdf6: function(e, t) { return Error(s(e, t)); },
        __wbg_new_with_length_a90559ebda3954f8: function(e) { return new Uint8Array(e >>> 0); },
        __wbg_node_84ea875411254db1: function(e) { return 0; },
        __wbg_now_cd850b0a28a6e656: function() { return Date.now(); },
        __wbg_process_44c7a14e11e9f69e: function(e) { return 0; },
        __wbg_prototypesetcall_7dca54d31cb9d2dc: function(e, t, n) { Uint8Array.prototype.set.call(i(e, t), n); },
        __wbg_randomFillSync_6c25eac9869eb53c: function() { return u(function(e, t) { e.randomFillSync(t); }, arguments); },
        __wbg_random_d9645defc0204485: function() { return Math.random(); },
        __wbg_removeChild_5fbc36e12df0c63a: function() { return u(function(e, t) { return e.removeChild(t); }, arguments); },
        __wbg_require_b4edbdcf3e2a1ef0: function() { return u(function() { return undefined; }, arguments); },
        __wbg_setAttribute_81f03c9a783fca26: function() { return u(function(e, t, n, r, i) { e.setAttribute(s(t, n), s(r, i)); }, arguments); },
        __wbg_set_id_e047efbc2bf2e248: function(e, t, n) { e.id = s(t, n); },
        __wbg_set_innerHTML_fb75cf5a1a8b7074: function(e, t, n) { e.innerHTML = s(t, n); },
        __wbg_static_accessor_GLOBAL_44bef9fa6011e260: function() { return 0; },
        __wbg_static_accessor_GLOBAL_THIS_13002645baf43d84: function() { return r(mockWindow); },
        __wbg_static_accessor_SELF_91d0abd4d035416c: function() { return r(mockWindow); },
        __wbg_static_accessor_WINDOW_513f857c65724fc7: function() { return r(mockWindow); },
        __wbg_subarray_fb60755cb1b4a498: function(e, t, n) { return e.subarray(t >>> 0, n >>> 0); },
        __wbg_userAgent_6dfab2ad96d4e4e4: function() { return u(function(e, t) { let n = t.userAgent, r = f(n, b.__wbindgen_malloc, b.__wbindgen_realloc), i = y; o().setInt32(e + 4, i, true); o().setInt32(e + 0, r, true); }, arguments); },
        __wbg_versions_276b2795b1c6a219: function(e) { return 0; },
        __wbindgen_cast_0000000000000001: function(e, t) { return i(e, t); },
        __wbindgen_cast_0000000000000002: function(e, t) { return s(e, t); },
        __wbindgen_init_externref_table: function() {
            let e = b.__wbindgen_externrefs, t = e.grow(4);
            e.set(0, undefined);
            e.set(t + 0, undefined);
            e.set(t + 1, null);
            e.set(t + 2, true);
            e.set(t + 3, false);
        }
    }
};

const wasmModule = new WebAssembly.Module(wasmBuffer);
const wasmInstance = new WebAssembly.Instance(wasmModule, imports);
b = wasmInstance.exports;
b.__wbindgen_start();

function wasmSign(appId, queryString) {
    let n, r;
    try {
        let o_val = f(appId, b.__wbindgen_malloc, b.__wbindgen_realloc);
        let c_val = y;
        let l_val = f(queryString, b.__wbindgen_malloc, b.__wbindgen_realloc);
        let u_val = y;
        let d_val = b.sign(o_val, c_val, l_val, u_val);
        var i_val = d_val[0], a_val = d_val[1];
        if (d_val[3]) throw (i_val = 0, a_val = 0, p(d_val[2]));
        return n = i_val, r = a_val, s(i_val, a_val);
    } finally {
        b.__wbindgen_free(n, r, 1);
    }
}

if (require.main === module) {
    let inputStr = process.argv[2];
    if (!inputStr) {
        inputStr = fs.readFileSync(0, 'utf-8');
    }
    const { appId, queryString } = JSON.parse(inputStr);
    const signature = wasmSign(appId, queryString);
    process.stdout.write(JSON.stringify({ signature }));
}

module.exports = { wasmSign };

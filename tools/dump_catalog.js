// Prints the catalogue (CATS, APPS, TOOLS) from site/assets/catalog.js as JSON, for the page generator.
const fs = require("fs"), vm = require("vm"), path = require("path");
const file = path.join(process.argv[2] || "site", "assets", "catalog.js");
const src = fs.readFileSync(file, "utf8");
const cut = src.indexOf("\n(function () {");
const ctx = {};
vm.runInNewContext(src.slice(0, cut) + "\n;this.__out = JSON.stringify({CATS: CATS, APPS: APPS, TOOLS: TOOLS});", ctx);
process.stdout.write(ctx.__out);

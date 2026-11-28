import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

test("abysshub has no runtime dependencies", async () => {
  const pkg = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
  assert.equal(pkg.name, "abysshub");
  assert.deepEqual(Object.keys(pkg.dependencies ?? {}), []);
});

test("abysshub's npm page says the job, carries keywords and links to the Docs", async () => {
  const pkg = JSON.parse(await readFile(new URL("../package.json", import.meta.url), "utf8"));
  assert.match(pkg.description, /Abyss Widget/);
  assert.ok(["abyss", "abysshub", "widget"].every((word) => pkg.keywords.includes(word)));
  assert.equal(pkg.homepage, "https://abysshub.com/docs#api");
  assert.equal(pkg.repository.url, "git+https://github.com/Abysshub/abysshub-sdk.git");
});

test("the built types carry a doc comment on each public member an editor shows", async () => {
  const { default: ts } = await import("typescript");
  const dist = (name) => fileURLToPath(new URL(`../dist/${name}.d.ts`, import.meta.url));
  const program = ts.createProgram([dist("index"), dist("types"), dist("files")], { noEmit: true });
  const checker = program.getTypeChecker();
  const exported = (module, name) => {
    const symbol = checker.getExportsOfModule(checker.getSymbolAtLocation(program.getSourceFile(dist(module)))).find((s) => s.name === name);
    assert.ok(symbol, `${module} exports no ${name}`);
    return symbol.flags & ts.SymbolFlags.Alias ? checker.getAliasedSymbol(symbol) : symbol;
  };
  const member = (symbol, name) => {
    const found = symbol.members?.get(name) ?? checker.getDeclaredTypeOfSymbol(symbol).getProperty(name);
    assert.ok(found, `${symbol.name} has no ${name}`);
    return found;
  };
  const undocumented = [
    ["index", "Runs"],
    ["index", "Widgets", "get"],
    ["index", "Uploads", "create"],
    ["index", "Abyss", "key"],
    ["index", "Run"],
    ["index", "RunFile"],
    ["index", "RunFile", "save"],
    ["index", "Widget"],
    ["index", "Widget", "input_schema"],
    ["index", "FileData"],
    ["types", "RunData"],
    ["types", "RunFileData"],
    ["files", "Uploader"],
  ].filter(([module, name, prop]) => {
    const symbol = exported(module, name);
    return ts.displayPartsToString((prop ? member(symbol, prop) : symbol).getDocumentationComment(checker)).trim() === "";
  });
  assert.deepEqual(undocumented, []);
});

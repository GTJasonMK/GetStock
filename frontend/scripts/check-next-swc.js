const os = require("os");
const fs = require("fs");
const path = require("path");

function readJson(filePath) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch (error) {
    return null;
  }
}

function normalizeVersion(raw) {
  let s = String(raw || "").trim();
  while (s && "^~<>=".includes(s[0])) {
    s = s.slice(1).trim();
  }
  return s.split(" ")[0].trim();
}

function getExpectedNextVersion(projectRoot) {
  const installedNext = readJson(path.join(projectRoot, "node_modules", "next", "package.json"));
  if (installedNext && typeof installedNext.version === "string" && installedNext.version.trim()) {
    return installedNext.version.trim();
  }

  const frontendPkg = readJson(path.join(projectRoot, "package.json"));
  if (!frontendPkg || typeof frontendPkg !== "object") {
    return "";
  }

  const nextRaw = frontendPkg.dependencies && frontendPkg.dependencies.next;
  if (typeof nextRaw !== "string") {
    return "";
  }

  return normalizeVersion(nextRaw);
}

function getExpectedSwcVersion(projectRoot, swcPkgName) {
  const installedNext = readJson(path.join(projectRoot, "node_modules", "next", "package.json"));
  if (!installedNext || typeof installedNext !== "object") return "";

  const optionalDeps = installedNext.optionalDependencies;
  if (!optionalDeps || typeof optionalDeps !== "object") return "";

  const raw = optionalDeps[swcPkgName];
  if (typeof raw !== "string") return "";

  return normalizeVersion(raw);
}

function getCandidates(platform, arch) {
  if (platform === "win32") {
    if (["x64", "amd64"].includes(arch)) return ["@next/swc-win32-x64-msvc"];
    if (["arm64", "aarch64"].includes(arch)) return ["@next/swc-win32-arm64-msvc"];
    if (["ia32", "x86"].includes(arch)) return ["@next/swc-win32-ia32-msvc"];
    return [];
  }

  if (platform === "linux") {
    if (["x64", "amd64"].includes(arch)) return ["@next/swc-linux-x64-gnu", "@next/swc-linux-x64-musl"];
    if (["arm64", "aarch64"].includes(arch)) return ["@next/swc-linux-arm64-gnu", "@next/swc-linux-arm64-musl"];
    if (["arm", "armv7l"].includes(arch)) return ["@next/swc-linux-arm-gnueabihf"];
    return [];
  }

  if (platform === "darwin") {
    if (["arm64", "aarch64"].includes(arch)) return ["@next/swc-darwin-arm64"];
    if (["x64", "amd64"].includes(arch)) return ["@next/swc-darwin-x64"];
    return [];
  }

  return [];
}

const platform = process.platform;
const arch = os.arch();
const candidates = getCandidates(platform, arch);
const projectRoot = process.cwd();
const expectedNextVersion = getExpectedNextVersion(projectRoot);

if (candidates.length === 0) {
  console.log(`[check-swc] 跳过：未识别平台 ${platform}/${arch}`);
  process.exit(0);
}

const found = [];
const mismatched = [];
const missing = [];

for (const name of candidates) {
  try {
    const pkgJsonPath = require.resolve(`${name}/package.json`);
    const pkgJson = readJson(pkgJsonPath);
    const swcVersion = pkgJson && typeof pkgJson.version === "string" ? pkgJson.version.trim() : "";
    const expectedSwcVersion = getExpectedSwcVersion(projectRoot, name);

    // Next 的 swc 版本不一定与 next 自身版本一致（以 next 的 optionalDependencies 为准）。
    if (!expectedSwcVersion || !swcVersion || swcVersion === expectedSwcVersion) {
      found.push(`${name}${swcVersion ? `@${swcVersion}` : ""}`);
      continue;
    }

    mismatched.push(`${name}@${swcVersion}${expectedSwcVersion ? ` (expected ${expectedSwcVersion})` : ""}`);
  } catch (error) {
    missing.push(name);
  }
}

if (found.length > 0) {
  if (expectedNextVersion) {
    console.log(`[check-swc] OK: ${found.join(", ")} (next@${expectedNextVersion})`);
  } else {
    console.log(`[check-swc] OK: ${found.join(", ")}`);
  }
  process.exit(0);
}

if (mismatched.length > 0) {
  console.error(`[check-swc] SWC 版本与 next 的依赖约束不一致: ${mismatched.join(", ")}`);
}

console.error(`[check-swc] 当前平台缺少 SWC 二进制: ${missing.join(", ")}`);
console.error("[check-swc] 请重新安装依赖: npm ci --prefer-offline --no-audit --no-fund");
process.exit(1);

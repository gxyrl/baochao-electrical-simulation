#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一键推送到 GitHub。

用法：双击同目录下的「推送.bat」。

流程：
  1. 检查本地是否有未提交改动 -> 有则自动 add + commit
  2. 读取远程当前状态，比对内容哈希
  3. 只上传有变化的文件（增量），创建新 commit 并移动分支

为什么不用 git push：
  本机网络对 github.com 主域名有 SNI 阻断，git push/clone 走 https 会失败；
  而 api.github.com 可正常访问，故改用 GitHub Git Data API 完成推送。
"""
import os
import sys
import json
import base64
import shutil
import subprocess
import datetime
import urllib.request
import urllib.error

# 统一输出编码为 UTF-8 —— 与「推送.bat」里的 chcp 65001 配合，
# 避免中文在 cmd 窗口里变成乱码（否则会出现 Python 输出 UTF-8、
# 而 cmd 自身的 pause 提示走 GBK 的混编局面）。
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# ==================== 配置 ====================
REPO   = "gxyrl/baochao-electrical-simulation"
BRANCH = "main"
API    = "https://api.github.com"
# ==============================================

REPO_DIR = os.path.dirname(os.path.abspath(__file__))


def log(msg=""):
    print(msg, flush=True)


# ---------------------------------------------------------------- git 定位
def find_git():
    """多级探测 git.exe，返回路径；找不到返回 None。"""
    cands = []

    g = shutil.which("git")
    if g:
        cands.append(g)

    for p in (r"C:\Program Files\Git\cmd\git.exe",
              r"C:\Program Files (x86)\Git\cmd\git.exe"):
        if os.path.isfile(p):
            cands.append(p)

    # WorkBuddy 自带的 PortableGit（本机最常见）
    base = os.path.expanduser(r"~\.workbuddy\binaries\PortableGit\versions")
    if os.path.isdir(base):
        for d in sorted(os.listdir(base), reverse=True):
            p = os.path.join(base, d, "cmd", "git.exe")
            if os.path.isfile(p):
                cands.append(p)

    # 当前脚本所在环境旁的 python 目录下也可能有
    for extra in (r"C:\Program Files\Git\bin\git.exe",):
        if os.path.isfile(extra):
            cands.append(extra)

    return cands[0] if cands else None


GIT = find_git()

ENV = dict(os.environ)
ENV["GIT_TERMINAL_PROMPT"] = "0"      # 禁止 git 交互式索要凭据（避免卡死）


def git(*args, binary=False, check=True):
    p = subprocess.run([GIT] + list(args), cwd=REPO_DIR,
                       capture_output=True, env=ENV)
    if check and p.returncode != 0:
        raise RuntimeError("git " + " ".join(args) + " 失败:\n"
                           + p.stderr.decode("utf-8", "replace"))
    return p.stdout if binary else p.stdout.decode("utf-8", "replace").strip()


# ---------------------------------------------------------------- 凭据
def get_token():
    """从 Windows 凭据管理器取出 GitHub token。"""
    p = subprocess.run([GIT, "credential", "fill"],
                       input="protocol=https\nhost=github.com\n\n",
                       capture_output=True, text=True, encoding="utf-8",
                       env=ENV, timeout=30)
    for line in p.stdout.splitlines():
        if line.startswith("password="):
            return line[len("password="):]
    return None


# ---------------------------------------------------------------- API
class Api:
    def __init__(self, token):
        self.h = {
            "Authorization": "token " + token,
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "User-Agent": "push-to-github-script",
        }

    def __call__(self, method, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(API + path, data=data, method=method,
                                     headers=self.h)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
                return r.status, (json.loads(body) if body else None)
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")[:400]
        except Exception as e:
            return -1, str(e)[:400]


# ---------------------------------------------------------------- 步骤
def step_commit():
    """有改动就自动提交，返回是否产生了新提交。"""
    status = git("status", "--porcelain")
    if not status:
        log("  [1/3] 工作区干净，无需提交")
        return False

    changed = len([l for l in status.splitlines() if l.strip()])
    log("  [1/3] 检测到 %d 处改动，正在提交..." % changed)
    git("add", "-A")

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    msg = "更新（%s）" % stamp
    git("commit", "-m", msg)
    log("        已提交：%s" % msg)
    return True


def step_push(api):
    """增量推送到 GitHub，返回远程新 HEAD。"""
    head = git("rev-parse", "HEAD")

    # 本地文件清单（mode, sha, path）
    entries = []
    for item in git("ls-tree", "-r", "-z", "--long", "HEAD").split("\0"):
        if not item.strip():
            continue
        meta, path = item.split("\t", 1)
        parts = meta.split()
        entries.append((parts[0], parts[2], path))

    # 远程当前 HEAD / tree
    st, ref = api("GET", "/repos/%s/git/ref/heads/%s" % (REPO, BRANCH))
    if st != 200:
        raise RuntimeError("读取远程分支失败 (%s): %s" % (st, ref))
    remote_commit = ref["object"]["sha"]

    st, rc = api("GET", "/repos/%s/git/commits/%s" % (REPO, remote_commit))
    if st != 200:
        raise RuntimeError("读取远程 commit 失败 (%s): %s" % (st, rc))
    remote_tree = rc["tree"]["sha"]

    # 递归收集远程 path -> blob sha
    remote_blobs = {}

    def walk(tree_sha, prefix=""):
        st, t = api("GET", "/repos/%s/git/trees/%s" % (REPO, tree_sha))
        if st != 200:
            return
        for e in t.get("tree", []):
            p = prefix + e["path"]
            if e["type"] == "tree":
                walk(e["sha"], p + "/")
            else:
                remote_blobs[p] = e["sha"]

    walk(remote_tree)

    local_blob = {path: sha for _, sha, path in entries}
    to_upload = [(path, sha) for path, sha in local_blob.items()
                 if remote_blobs.get(path) != sha]

    log("  [2/3] 本地 %d 个文件 / 远程 %d 个文件，需上传 %d 个"
        % (len(entries), len(remote_blobs), len(to_upload)))

    blob_map = {}
    for path, sha in local_blob.items():
        if remote_blobs.get(path) == sha:
            blob_map[path] = sha     # 复用远程已有对象

    for i, (path, sha) in enumerate(to_upload, 1):
        content = git("cat-file", "blob", sha, binary=True)
        b64 = base64.b64encode(content).decode("ascii")
        st, res = api("POST", "/repos/%s/git/blobs" % REPO,
                      {"content": b64, "encoding": "base64"})
        if st != 201:
            raise RuntimeError("上传 %s 失败 (%s): %s" % (path, st, res))
        blob_map[path] = res["sha"]
        log("        [%d/%d] %s" % (i, len(to_upload), path))

    # 自底向上建 tree
    root = {}
    for mode, _sha, path in entries:
        parts = path.split("/")
        node = root
        for seg in parts[:-1]:
            node = node.setdefault(seg, {})
        node[parts[-1]] = (mode, blob_map[path])

    def build(node):
        items = []
        for name, val in node.items():
            if isinstance(val, dict):
                st, res = api("POST", "/repos/%s/git/trees" % REPO,
                              {"tree": build(val)})
                if st != 201:
                    raise RuntimeError("建树 %s 失败 (%s): %s" % (name, st, res))
                items.append({"path": name, "mode": "040000",
                              "type": "tree", "sha": res["sha"]})
            else:
                mode, bsha = val
                items.append({"path": name, "mode": mode,
                              "type": "blob", "sha": bsha})
        return items

    st, res = api("POST", "/repos/%s/git/trees" % REPO, {"tree": build(root)})
    if st != 201:
        raise RuntimeError("建立根 tree 失败 (%s): %s" % (st, res))
    new_tree = res["sha"]

    if new_tree == remote_tree:
        log("        远程内容与本地一致，无需推送")
        return remote_commit, False

    # 创建 commit
    msg = git("log", "-1", "--format=%B")
    an = git("log", "-1", "--format=%an")
    ae = git("log", "-1", "--format=%ae")
    ad = git("log", "-1", "--format=%aI")

    st, res = api("POST", "/repos/%s/git/commits" % REPO, {
        "message": msg, "tree": new_tree, "parents": [remote_commit],
        "author": {"name": an, "email": ae, "date": ad},
        "committer": {"name": an, "email": ae, "date": ad},
    })
    if st != 201:
        raise RuntimeError("创建 commit 失败 (%s): %s" % (st, res))
    new_commit = res["sha"]

    st, res = api("PATCH", "/repos/%s/git/refs/heads/%s" % (REPO, BRANCH),
                  {"sha": new_commit, "force": True})
    if st != 200:
        raise RuntimeError("更新分支失败 (%s): %s" % (st, res))

    log("  [3/3] 推送完成")
    log("        远程 HEAD: %s" % new_commit[:12])
    log("        内容校验: 远程 tree 与本地 %s"
        % ("一致 ✓" if new_tree == git("rev-parse", "HEAD^{tree}") else "不一致 ✗"))

    # 顺手建立远程跟踪引用，便于日后比对
    try:
        git("update-ref", "refs/remotes/origin/%s" % BRANCH, new_commit)
    except Exception:
        pass

    return new_commit, True


def main():
    log("=" * 52)
    log("  推送到 GitHub  —  %s" % REPO)
    log("=" * 52)
    log()

    # --- 环境检查 ---
    if not GIT:
        log("[错误] 未找到 git.exe，无法继续。")
        log("       请安装 Git，或确认 PortableGit 存在。")
        return 1
    if not os.path.isdir(os.path.join(REPO_DIR, ".git")):
        log("[错误] 当前目录不是 git 仓库：%s" % REPO_DIR)
        return 1

    token = get_token()
    if not token:
        log("[错误] 无法获取 GitHub 凭据。")
        log("       请先在任意 git 仓库执行一次推送，让系统记住凭据。")
        return 1

    log("  git    : %s" % GIT)
    log("  仓库   : %s" % REPO_DIR)
    log()

    try:
        step_commit()
        api = Api(token)
        new_commit, pushed = step_push(api)
    except Exception as e:
        log()
        log("[失败] %s" % e)
        return 1

    log()
    log("-" * 52)
    log("  完成！%s" % ("已推送新内容" if pushed else "远程本来就是最新的"))
    log("  仓库地址: https://github.com/%s" % REPO)
    log("-" * 52)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\n已取消")
        sys.exit(130)

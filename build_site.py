#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把媒体知识库的逐字稿发布成 GitHub Pages 静态站。

流程：
  1. 扫 `D:\\视频\\媒体知识库\\博主\\<作者>\\*.md`，解析头部字段（作者/抖音账号/作品ID/标题/时间/关键词）
  2. 逐字稿 md 原样复制到 `transcripts/<作者>/`（Pages 直接当页面渲染，天然支持中文文件名）
  3. 封面用 Pillow 缩到宽 720px + JPEG q82，输出到 `assets/covers/<作者>/<同名>.jpg`
  4. 生成 `data/transcripts.json`（全量元数据 + 摘要正文），供前端列表/搜索/筛选
  5. 渲染静态壳：`index.html`（首页）、`authors.html`（按主播）、`doc.html`（单篇壳）
  6. 写 `.nojekyll`（避免 GitHub Pages 忽略下划线目录）

用法：
  python build_site.py            # 全量构建
  python build_site.py --covers   # 只重压封面
  python build_site.py --pages    # 只重生成页面（跳过复制/压缩）
"""

import argparse
import html
import json
import os
import re
import shutil
import sys
import time

SRC_ROOT = r"D:\视频\媒体知识库\博主"
OUT_ROOT = r"D:\视频\douyin-transcripts-site"

TR_DIR = os.path.join(OUT_ROOT, "transcripts")
ASSETS = os.path.join(OUT_ROOT, "assets")
COVER_DIR = os.path.join(ASSETS, "covers")
DATA_DIR = os.path.join(OUT_ROOT, "data")

COVER_MAX_W = 720
COVER_QUALITY = 82

IMG_EXT = (".jpg", ".jpeg", ".webp", ".png")


# ---------------------------------------------------------------- 解析

FIELD_RE = re.compile(r"^([一-龥A-Za-z0-9]+)：(.*)$")
SEP = "-" * 5


def parse_md(path):
    """解析 md：头部字段 + 三段式总结 + 逐字稿正文。

    头部形如 `作者：巫师财经`，逐行到第一个 `-----` 为止。
    """
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    lines = raw.split("\n")
    fields = {}
    i = 0
    for i, ln in enumerate(lines[:40]):
        s = ln.strip()
        if s.startswith(SEP):
            break
        m = FIELD_RE.match(s)
        if m:
            fields[m.group(1).strip()] = m.group(2).strip()

    # 总结块：第一个 ----- 与第二个 ----- 之间
    seps = [j for j, ln in enumerate(lines) if ln.strip().startswith(SEP)]
    summary = ""
    transcript = ""
    if len(seps) >= 2:
        summary = "\n".join(lines[seps[0] + 1:seps[1]]).strip()
        transcript = "\n".join(lines[seps[1] + 1:]).strip()
    elif len(seps) == 1:
        summary = "\n".join(lines[seps[0] + 1:]).strip()

    cover = ""
    m = re.search(r"视频封面：!\[封面\]\(([^)]+)\)", raw)
    if m:
        cover = m.group(1).strip()

    return fields, summary, transcript, cover


def douyin_home(account):
    """抖音账号字段 → 主页链接。支持 uniqueId / 数字ID / sec_uid。"""
    if not account:
        return ""
    return "https://www.douyin.com/user/%s" % account


def douyin_video(work_id):
    m = re.search(r"(\d{15,})", work_id or "")
    if not m:
        return ""
    return "https://www.douyin.com/video/%s" % m.group(1)


# ---------------------------------------------------------------- 封面压缩

def compress_cover(src, dst):
    """缩到宽 <= COVER_MAX_W 并转 JPEG。失败返回 False。"""
    from PIL import Image

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    try:
        with Image.open(src) as im:
            im = im.convert("RGB")
            if im.width > COVER_MAX_W:
                h = max(1, round(im.height * COVER_MAX_W / im.width))
                im = im.resize((COVER_MAX_W, h), Image.LANCZOS)
            im.save(dst, "JPEG", quality=COVER_QUALITY, optimize=True, progressive=True)
        return True
    except Exception as e:
        sys.stderr.write("[cover-fail] %s: %s\n" % (src, e))
        return False


# ---------------------------------------------------------------- 采集

def collect(do_copy=True, do_covers=True):
    if not os.path.isdir(SRC_ROOT):
        sys.exit("源目录不存在: %s" % SRC_ROOT)

    items = []
    authors = {}
    stats = {"md": 0, "cover_ok": 0, "cover_skip": 0, "cover_fail": 0}
    t0 = time.time()

    for author in sorted(os.listdir(SRC_ROOT)):
        adir = os.path.join(SRC_ROOT, author)
        if not os.path.isdir(adir) or author.startswith(("_", ".")):
            continue

        docs = []
        for fn in sorted(os.listdir(adir)):
            if not fn.endswith(".md"):
                continue
            src = os.path.join(adir, fn)
            stem = fn[:-3]
            fields, summary, transcript, cover = parse_md(src)

            doc = {
                "id": "%s/%s" % (author, stem),
                "author": author,
                "title": fields.get("视频标题") or stem,
                "url": fields.get("作品ID") or "",
                "date": fields.get("发布时间") or stem[:10],
                "keywords": [k for k in re.split(r"[、,，]", fields.get("关键词") or "") if k.strip()],
                "account": fields.get("抖音账号") or "",
                "chars": len(transcript),
                "summary": summary,
                "transcript": transcript,
                "cover": "",
            }
            doc["videoUrl"] = douyin_video(doc["url"])
            doc["homeUrl"] = douyin_home(doc["account"])

            # 封面
            src_cover = ""
            for ext in IMG_EXT:
                cand = os.path.join(adir, stem + ext)
                if os.path.isfile(cand):
                    src_cover = cand
                    break
            if not src_cover and cover:
                cand = os.path.join(adir, cover)
                if os.path.isfile(cand):
                    src_cover = cand

            if src_cover:
                rel = "assets/covers/%s/%s.jpg" % (author, stem)
                dst = os.path.join(OUT_ROOT, rel.replace("/", os.sep))
                doc["cover"] = rel
                need = do_covers or not os.path.isfile(dst)
                if need:
                    if compress_cover(src_cover, dst):
                        stats["cover_ok"] += 1
                    else:
                        stats["cover_fail"] += 1
                        doc["cover"] = ""
                else:
                    stats["cover_skip"] += 1

            # 复制 md（Pages 会渲染 md 源不如预渲染，但保留原文件便于下载/追溯）
            if do_copy:
                ddir = os.path.join(TR_DIR, author)
                os.makedirs(ddir, exist_ok=True)
                shutil.copy2(src, os.path.join(ddir, fn))

            docs.append(doc)
            stats["md"] += 1
            if stats["md"] % 100 == 0:
                print("  ... %d 篇 (%.0fs)" % (stats["md"], time.time() - t0))

        if docs:
            docs.sort(key=lambda d: (d["date"], d["id"]), reverse=True)
            authors[author] = docs

    return authors, stats


# ---------------------------------------------------------------- 页面

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#f5f6f8;--card:#fff;--line:#e5e7eb;--txt:#1f2328;--dim:#6b7280;
 --accent:#2563eb;--ok:#16a34a;--soft:#f3f4f6;--warn:#d97706}
body{background:var(--bg);color:var(--txt);
 font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;
 -webkit-font-smoothing:antialiased}
a{color:var(--accent);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1160px;margin:0 auto;padding:22px 20px 70px}
header.top{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin-bottom:22px}
header.top h1{font-size:20px;font-weight:700}
header.top .sp{flex:1}
.badge{background:var(--soft);color:var(--dim);border-radius:999px;padding:3px 11px;font-size:12.5px}
.badge.nav-on{background:var(--accent);color:#fff}
.grid{display:grid;gap:14px}
.g4{grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.stat{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
.stat .k{font-size:12.5px;color:var(--dim);margin-bottom:6px}
.stat .v{font-size:26px;font-weight:700;letter-spacing:-.5px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin-bottom:16px}
.card h2{font-size:15px;font-weight:700;margin-bottom:14px;display:flex;align-items:center;gap:9px;flex-wrap:wrap}
input[type=search],select{font:inherit;padding:9px 13px;border:1px solid var(--line);
 border-radius:9px;background:var(--card);color:var(--txt);outline:none}
input[type=search]{flex:1;min-width:220px}
input[type=search]:focus,select:focus{border-color:var(--accent)}
.tools{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:16px}
.docs{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(232px,1fr))}
.doc{background:var(--card);border:1px solid var(--line);border-radius:11px;overflow:hidden;
 display:flex;flex-direction:column;transition:.14s}
.doc:hover{border-color:var(--accent);transform:translateY(-2px);box-shadow:0 6px 18px rgba(0,0,0,.07)}
.doc .cv{aspect-ratio:16/10;background:var(--soft);overflow:hidden;display:block}
.doc .cv img{width:100%;height:100%;object-fit:cover;display:block}
.doc .no{aspect-ratio:16/10;display:flex;align-items:center;justify-content:center;
 color:var(--dim);font-size:12.5px;background:var(--soft)}
.doc .b{padding:10px 12px 12px;display:flex;flex-direction:column;gap:6px;flex:1}
.doc .au{font-size:11.5px;color:var(--dim)}
.doc .ti{font-size:13.5px;font-weight:600;line-height:1.5;
 display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.doc .mt{display:flex;gap:7px;align-items:center;font-size:11.5px;color:var(--dim);margin-top:auto}
.kw{background:var(--soft);border-radius:5px;padding:1px 6px;font-size:11px;color:var(--dim)}
.authors{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(258px,1fr))}
.author{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;display:block;color:inherit}
.author:hover{border-color:var(--accent);text-decoration:none;box-shadow:0 5px 16px rgba(0,0,0,.06)}
.author .n{font-size:15.5px;font-weight:700;margin-bottom:6px}
.author .m{font-size:12.5px;color:var(--dim)}
.author .avs{display:flex;gap:5px;margin-top:11px;flex-wrap:wrap}
.author .avs img{width:44px;height:44px;object-fit:cover;border-radius:7px;border:1px solid var(--line)}
.author .lk{font-size:12px;color:var(--accent);margin-top:10px;display:inline-block}
.empty{text-align:center;color:var(--dim);padding:60px 20px}
footer{color:var(--dim);font-size:12.5px;text-align:center;margin-top:44px;line-height:2}
mark{background:#fff3a3;color:inherit;padding:0 1px;border-radius:2px}
"""

JS = """
function fmtDur(s){
  s = Math.round(s||0);
  var h = Math.floor(s/3600), m = Math.floor(s%3600/60);
  return h ? (h+' 小时 '+(m?m+' 分':'')) : (m+' 分');
}
function esc(s){return (s==null?'':String(s)).replace(/[&<>"']/g,function(c){
  return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
function hl(text, kw){
  if(!kw) return esc(text);
  try{
    var re = new RegExp('('+kw.replace(/[.*+?^${}()|[\\]\\\\]/g,'\\\\$&')+')','gi');
    return esc(text).replace(re,'<mark>$1</mark>');
  }catch(e){return esc(text);}
}
function coverHtml(d){
  return d.cover
    ? '<a class="cv" href="doc.html?id='+encodeURIComponent(d.id)+'"><img loading="lazy" src="'+d.cover+'" alt=""></a>'
    : '<a class="no" href="doc.html?id='+encodeURIComponent(d.id)+'">无封面</a>';
}
function docHtml(d, kw){
  return '<article class="doc">'+coverHtml(d)+
   '<div class="b"><span class="au">'+esc(d.author)+' · '+esc(d.date)+'</span>'+
   '<a class="ti" href="doc.html?id='+encodeURIComponent(d.id)+'">'+hl(d.title,kw)+'</a>'+
   '<div class="mt"><span>'+fmtDur(d.chars/4.5)+'字</span>'+
   (d.keywords&&d.keywords[0]?'<span class="kw">'+esc(d.keywords[0])+'</span>':'')+
   '</div></div></article>';
}
"""


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def shell(title, body, script, active):
    nav = (
        '<a class="badge%s" href="index.html">📊 全部</a>\n'
        '<a class="badge%s" href="authors.html">👤 按主播</a>\n'
        '<a class="badge%s" href="index.html#kw">🔖 关键词</a>'
    ) % (
        " nav-on" if active == "home" else "",
        " nav-on" if active == "auth" else "",
        " nav-on" if active == "kw" else "",
    )
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<title>%s</title><style>%s</style></head><body><div class="wrap">\n'
        '<header class="top"><h1><a href="index.html" style="color:inherit">📚 抖音逐字稿库</a></h1>'
        '<span class="sp"></span>%s</header>\n%s\n<script>%s</script></div></body></html>'
    ) % (html.escape(title), CSS, nav, body, script)


def gen_index(meta):
    body = """
<div class="grid g4">
  <div class="stat"><div class="k">逐字稿</div><div class="v">%(docs)d</div></div>
  <div class="stat"><div class="k">主播</div><div class="v">%(authors)d</div></div>
  <div class="stat"><div class="k">总字数</div><div class="v">%(chars)s</div></div>
  <div class="stat"><div class="k">关键词</div><div class="v">%(kws)d</div></div>
</div>

<div class="tools" style="margin-top:18px">
  <input type="search" id="q" placeholder="🔍 搜索标题 / 摘要 / 逐字稿 / 主播 / 关键词…" autocomplete="off">
  <select id="au"><option value="">全部主播</option></select>
  <select id="kw"><option value="">全部关键词</option></select>
  <select id="so">
    <option value="date">最新优先</option>
    <option value="chars">字数最多</option>
    <option value="title">标题 A→Z</option>
  </select>
</div>

<div class="card">
  <h2>逐字稿 <span class="badge" id="cnt"></span></h2>
  <div class="docs" id="list"></div>
  <div class="empty" id="none" style="display:none">没有匹配的逐字稿</div>
</div>
""" % {
        "docs": meta["docs"],
        "authors": meta["authors"],
        "chars": "%.1f万" % (meta["chars"] / 10000.0) if meta["chars"] else "0",
        "kws": len(meta["keywords"]),
    }

    script = JS + """
var DATA = null, LIST = [], q='', au='', kw='';
fetch('data/transcripts.json').then(function(r){return r.json();}).then(function(d){
  DATA = d; LIST = d.docs;
  var auSel = document.getElementById('au');
  d.authorList.forEach(function(a){
    var o = document.createElement('option'); o.value = a.name; o.textContent = a.name + ' (' + a.docs + ')';
    auSel.appendChild(o);
  });
  var kwSel = document.getElementById('kw');
  d.keywords.slice(0, 400).forEach(function(k){
    var o = document.createElement('option'); o.value = k; o.textContent = k;
    kwSel.appendChild(o);
  });
  bind(); render();
});
function bind(){
  var t;
  document.getElementById('q').addEventListener('input', function(){
    clearTimeout(t); var v = this.value.trim();
    t = setTimeout(function(){ q = v.toLowerCase(); render(); }, 160);
  });
  document.getElementById('au').addEventListener('change', function(){ au = this.value; render(); });
  document.getElementById('kw').addEventListener('change', function(){ kw = this.value; render(); });
  document.getElementById('so').addEventListener('change', render);
  if (location.hash === '#kw') document.getElementById('kw').focus();
}
function match(d){
  if (au && d.author !== au) return false;
  if (kw && (d.keywords||[]).indexOf(kw) < 0) return false;
  if (!q) return true;
  if (d.title.toLowerCase().indexOf(q) >= 0) return true;
  if (d.author.toLowerCase().indexOf(q) >= 0) return true;
  if ((d.keywords||[]).some(function(k){return k.toLowerCase().indexOf(q) >= 0;})) return true;
  if (d.summary && d.summary.toLowerCase().indexOf(q) >= 0) return true;
  if (d.transcript && d.transcript.toLowerCase().indexOf(q) >= 0) return true;
  return false;
}
function render(){
  var so = document.getElementById('so').value;
  var out = LIST.filter(match);
  out.sort(function(a,b){
    if (so === 'chars') return b.chars - a.chars;
    if (so === 'title') return a.title.localeCompare(b.title,'zh');
    return (a.date < b.date ? 1 : a.date > b.date ? -1 : 0);
  });
  var box = document.getElementById('list');
  document.getElementById('cnt').textContent = out.length + ' 篇';
  document.getElementById('none').style.display = out.length ? 'none' : '';
  var kwh = q;
  box.innerHTML = out.slice(0, 600).map(function(d){return docHtml(d, kwh);}).join('');
  if (out.length > 600) {
    var n = document.createElement('div');
    n.className = 'empty'; n.textContent = '仅显示前 600 篇，请继续输入关键词缩小范围';
    box.appendChild(n);
  }
}
"""
    write(os.path.join(OUT_ROOT, "index.html"), shell("抖音逐字稿库", body, script, "home"))


def gen_authors(meta):
    body = """
<div class="card">
  <h2>按主播浏览 <span class="badge">%(n)d 位</span></h2>
  <div class="authors" id="grid"></div>
</div>
""" % {"n": meta["authors"]}

    script = JS + """
fetch('data/transcripts.json').then(function(r){return r.json();}).then(function(d){
  document.getElementById('grid').innerHTML = d.authorList.map(function(a){
    var avs = (a.covers||[]).slice(0,5).map(function(c){
      return '<img loading="lazy" src="'+c+'" alt="">';
    }).join('');
    return '<a class="author" href="index.html?au='+encodeURIComponent(a.name)+'">'+
      '<div class="n">'+esc(a.name)+'</div>'+
      '<div class="m">'+a.docs+' 篇 · '+fmtDur(a.chars/220)+'字 · 最早 '+a.first+' · 最新 '+a.last+'</div>'+
      (avs ? '<div class="avs">'+avs+'</div>' : '')+
      (a.homeUrl ? '<span class="lk">抖音主页 ↗</span>' : '')+'</a>';
  }).join('');
  // 兼容 query 直达
  var m = location.search.match(/[?&]au=([^&]+)/);
  if (m) { location.href = 'index.html?au=' + m[1]; }
});
"""
    write(os.path.join(OUT_ROOT, "authors.html"), shell("按主播 · 抖音逐字稿库", body, script, "auth"))


def gen_doc():
    body = """
<div id="crumb" style="font-size:13px;color:var(--dim);margin-bottom:14px"></div>
<article class="card" id="box" style="display:none">
  <div style="display:flex;gap:20px;flex-wrap:wrap">
    <a id="cv" style="flex:0 0 300px"><img id="cvi" style="width:100%;border-radius:10px;border:1px solid var(--line)"></a>
    <div style="flex:1;min-width:260px">
      <h1 id="ti" style="font-size:20px;line-height:1.5;margin-bottom:10px"></h1>
      <div id="mt" style="color:var(--dim);font-size:13px;margin-bottom:12px"></div>
      <div id="kws" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px"></div>
      <div style="display:flex;gap:10px;flex-wrap:wrap">
        <a class="badge" id="dl" download>⬇ 下载 md 原文</a>
        <a class="badge" id="vd" target="_blank" rel="noopener">▶ 抖音原视频</a>
        <a class="badge" id="hm" target="_blank" rel="noopener">👤 主播主页</a>
        <a class="badge" id="nx" rel="noopener">→ 下一篇</a>
      </div>
    </div>
  </div>
  <h2 style="margin:26px 0 12px;font-size:16px;font-weight:700">内容总结</h2>
  <div id="sm" style="font-size:14.5px"></div>
  <h2 style="margin:26px 0 12px;font-size:16px;font-weight:700">逐字稿 <span class="badge" id="tc"></span></h2>
  <div id="tr" style="font-size:15px;white-space:pre-wrap;line-height:2"></div>
</article>
<div class="empty" id="none">未找到该逐字稿</div>
"""
    script = JS + """
function md2html(s){
  return esc(s)
    .replace(/^### (.+)$/gm, '<h4 style="font-size:14.5px;margin:16px 0 8px">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 style="font-size:15.5px;margin:20px 0 10px">$1</h3>')
    .replace(/^- (.+)$/gm, '<li style="margin:5px 0 5px 18px">$1</li>');
}
fetch('data/transcripts.json').then(function(r){return r.json();}).then(function(d){
  var m = location.search.match(/[?&]id=([^&]+)/);
  if (!m) return;
  var id = decodeURIComponent(m[1]);
  var i = d.docs.findIndex(function(x){return x.id === id;});
  if (i < 0) return;
  var doc = d.docs[i];
  document.title = doc.title + ' · 抖音逐字稿库';
  document.getElementById('crumb').innerHTML =
    '<a href="index.html">全部</a> › <a href="index.html?au='+encodeURIComponent(doc.author)+'">'+esc(doc.author)+'</a>';
  document.getElementById('ti').textContent = doc.title;
  document.getElementById('mt').textContent = doc.author + ' · ' + doc.date + ' · ' + doc.chars + ' 字';
  document.getElementById('kws').innerHTML = (doc.keywords||[]).map(function(k){
    return '<a class="kw" href="index.html?kw='+encodeURIComponent(k)+'">'+esc(k)+'</a>';
  }).join('');
  if (doc.cover) {
    document.getElementById('cvi').src = doc.cover;
  } else {
    document.getElementById('cv').style.display = 'none';
  }
  document.getElementById('dl').href = 'transcripts/' + doc.id + '.md';
  var vd = document.getElementById('vd');
  if (doc.videoUrl) vd.href = doc.videoUrl; else vd.style.display = 'none';
  var hm = document.getElementById('hm');
  if (doc.homeUrl) hm.href = doc.homeUrl; else hm.style.display = 'none';
  var nx = document.getElementById('nx');
  var prev = d.docs[i-1], next = d.docs[i+1];
  nx.href = prev ? 'doc.html?id=' + encodeURIComponent(prev.id) : 'index.html';
  nx.textContent = prev ? '→ ' + prev.title.slice(0,14) : '→ 回到列表';
  document.getElementById('sm').innerHTML = md2html(doc.summary);
  document.getElementById('tr').textContent = doc.transcript || '（无逐字稿）';
  document.getElementById('tc').textContent = doc.chars + ' 字';
  document.getElementById('box').style.display = '';
  document.getElementById('none').style.display = 'none';
  window.scrollTo(0, 0);
});
"""
    write(os.path.join(OUT_ROOT, "doc.html"), shell("逐字稿 · 抖音逐字稿库", body, script, ""))


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--covers", action="store_true", help="强制重压封面")
    ap.add_argument("--pages", action="store_true", help="只重建页面")
    a = ap.parse_args()

    os.makedirs(OUT_ROOT, exist_ok=True)
    print("源: %s\n出: %s\n" % (SRC_ROOT, OUT_ROOT))

    if a.pages:
        with open(os.path.join(DATA_DIR, "transcripts.json"), "r", encoding="utf-8") as f:
            payload = json.load(f)
        stats = {"md": 0, "cover_ok": 0, "cover_skip": 0, "cover_fail": 0}
    else:
        print("扫描 + 压缩封面 + 复制 md ...")
        authors, stats = collect(do_copy=True, do_covers=a.covers)
        docs = [d for a_ in authors.values() for d in a_]
        docs.sort(key=lambda d: (d["date"], d["id"]), reverse=True)

        author_list = []
        for name, ds in authors.items():
            chars = sum(d["chars"] for d in ds)
            author_list.append({
                "name": name,
                "docs": len(ds),
                "chars": chars,
                "first": min(d["date"] for d in ds),
                "last": max(d["date"] for d in ds),
                "homeUrl": next((d["homeUrl"] for d in ds if d["homeUrl"]), ""),
                "covers": [d["cover"] for d in ds if d["cover"]][:5],
            })
        author_list.sort(key=lambda x: -x["docs"])

        kwc = {}
        for d in docs:
            for k in d["keywords"]:
                kwc[k] = kwc.get(k, 0) + 1
        keywords = sorted(kwc.items(), key=lambda x: (-x[1], x[0]))

        payload = {
            "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "docs": len(docs),
            "authors": len(author_list),
            "chars": sum(d["chars"] for d in docs),
            "keywords": [k for k, _ in keywords],
            "keywordCount": dict(keywords),
            "authorList": author_list,
            "docsList": docs,
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(os.path.join(DATA_DIR, "transcripts.json"), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    print("\n生成页面 ...")
    meta = {k: payload[k] for k in ("docs", "authors", "chars", "keywords")}
    gen_index(meta)
    gen_authors(meta)
    gen_doc()
    write(os.path.join(OUT_ROOT, ".nojekyll"), "")
    write(os.path.join(OUT_ROOT, "robots.txt"), "User-agent: *\nAllow: /\n")

    print("\n完成:")
    print("  逐字稿 %d 篇" % stats["md"])
    print("  封面  压新 %d / 复用 %d / 失败 %d" % (stats["cover_ok"], stats["cover_skip"], stats["cover_fail"]))
    if not a.pages:
        print("  json  %.1f MB" % (os.path.getsize(os.path.join(DATA_DIR, "transcripts.json")) / 1048576))


if __name__ == "__main__":
    main()

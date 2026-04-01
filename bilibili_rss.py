#!/usr/bin/env python3
"""
Bilibili UP主视频 RSS 生成器
从 B站获取视频列表并生成 RSS XML
"""

import hashlib
import json
import time
import uuid
import requests
from datetime import datetime, timezone, timedelta
import os
import sys

UID = os.environ.get("BILIBILI_UID", "24919812")
MAX_VIDEOS = int(os.environ.get("RSS_MAX_VIDEOS", "10"))
OUTPUT_FILE = "docs/rss.xml"

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52
]

def get_mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]

def enc_wbi(params: dict, img_key: str, sub_key: str) -> dict:
    mixin_key = get_mixin_key(img_key + sub_key)
    curr_time = int(time.time())
    params["wts"] = curr_time
    params = dict(sorted(params.items()))
    params = {k: "".join(c for c in str(v) if c.isalnum() or c in "-_.!~*'()")
              for k, v in params.items()}
    query = "&".join(f"{k}={v}" for k, v in params.items())
    params["w_rid"] = hashlib.md5((query + mixin_key).encode()).hexdigest()
    return params

def fetch_videos(uid: str, max_videos: int) -> list:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    })
    
    # 获取 cookies
    session.get("https://www.bilibili.com/")
    
    # 获取 WBI 密钥
    resp = session.get("https://api.bilibili.com/x/web-interface/nav")
    nav_data = resp.json()
    if nav_data.get("code") != 0:
        print(f"获取 WBI 密钥失败: {nav_data.get('message')}")
        return []
    
    img_url = nav_data["data"]["wbi_img"]["img_url"]
    sub_url = nav_data["data"]["wbi_img"]["sub_url"]
    img_key = img_url.rsplit("/", 1)[1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[1].split(".")[0]
    
    all_videos = []
    pn = 1
    
    while True:
        params = {
            "mid": uid,
            "ps": "30",
            "tid": "0",
            "pn": str(pn),
            "keyword": "",
            "order": "pubdate",
        }
        params = enc_wbi(params, img_key, sub_key)
        
        resp = session.get("https://api.bilibili.com/x/space/wbi/arc/search", params=params)
        data = resp.json()
        
        if data.get("code") != 0:
            print(f"API 错误: {data.get('message')}")
            break
        
        vlist = data["data"]["list"]["vlist"]
        if not vlist:
            break
        
        for v in vlist:
            pub_dt = datetime.fromtimestamp(v.get("created", 0))
            all_videos.append({
                "title": v["title"],
                "author": v.get("author", ""),
                "pic": v.get("pic", ""),
                "bvid": v["bvid"],
                "desc": v.get("description", ""),
                "pubdate": pub_dt,
            })
            if len(all_videos) >= max_videos:
                break
        
        if len(all_videos) >= max_videos:
            break
        
        total = data["data"]["page"].get("count", 0)
        if pn * 30 >= total:
            break
        pn += 1
    
    return all_videos

def xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

def build_rss(videos: list, uid: str, max_videos: int) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:media="http://search.yahoo.com/mrss/">')
    lines.append("  <channel>")
    lines.append(f"    <title>Bilibili UP {uid} 视频更新</title>")
    lines.append(f"    <link>https://space.bilibili.com/{uid}/video</link>")
    lines.append(f"    <description>B站UP主 {uid} 最近{max_videos}条视频更新</description>")
    lines.append(f"    <language>zh-CN</language>")
    lines.append(f"    <lastBuildDate>{datetime.now(timezone.utc).strftime('%a, %d %b %Y %H:%M:%S +0000')}</lastBuildDate>")
    lines.append(f'    <atom:link href="https://{os.environ.get("GITHUB_REPOSITORY", "user/repo").split("/")[0]}.github.io/bilibili-rss/rss.xml" rel="self" type="application/rss+xml"/>')

    for v in videos:
        desc = xml_escape(v["desc"] or v["title"])
        title = xml_escape(v["title"])
        author = xml_escape(v["author"])
        pic_url = xml_escape(v["pic"]) if v["pic"] else ""
        lines.append("    <item>")
        lines.append(f"      <title>{title}</title>")
        lines.append(f"      <link>https://www.bilibili.com/video/{v['bvid']}</link>")
        lines.append(f"      <guid>{v['bvid']}</guid>")
        lines.append(f"      <description>{desc}</description>")
        lines.append(f"      <pubDate>{v['pubdate'].strftime('%a, %d %b %Y %H:%M:%S +0800')}</pubDate>")
        lines.append(f"      <author>noreply@bilibili.com ({author})</author>")
        lines.append(f"      <category>Bilibili</category>")
        if pic_url:
            lines.append(f'      <media:thumbnail url="{pic_url}"/>')
        lines.append("    </item>")

    lines.append("  </channel>")
    lines.append("</rss>")
    return "\n".join(lines)

def main():
    print(f"获取 UP主 {UID} 最近 {MAX_VIDEOS} 条视频...")
    videos = fetch_videos(UID, MAX_VIDEOS)
    print(f"获取到 {len(videos)} 个视频")

    for v in videos:
        print(f"  - {v['title']} ({v['pubdate'].strftime('%Y-%m-%d %H:%M')})")

    rss_xml = build_rss(videos, UID, MAX_VIDEOS)

    os.makedirs("docs", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(rss_xml)
    print(f"\nRSS 已保存到 {OUTPUT_FILE}")

if __name__ == "__main__":
    main()

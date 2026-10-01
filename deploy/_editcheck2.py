import json
import time
import urllib.error
import urllib.request

KEY = "sa_zBEpBJSBoxwGT7MLvoe3QHcRsX7vk0Qm"
PUB = "http://47.109.30.40:8000"


def call(path, method="GET", body=None, timeout=400):
    h = {"Content-Type": "application/json", "X-API-Key": KEY}
    req = urllib.request.Request(PUB + path, method=method, headers=h,
                                 data=json.dumps(body).encode() if body else None)
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:200], "status": e.code}


print("顺序生成片段1…")
a = call("/video", "POST", {"prompt": "海浪拍打礁石，日落"})
print("片段1:", ("ok" if a.get("ok") else "FAIL"), (a.get("url") or "")[:60])
time.sleep(3)
print("顺序生成片段2…")
b = call("/video", "POST", {"prompt": "无人机飞越森林，晨雾"})
print("片段2:", ("ok" if b.get("ok") else "FAIL"), (b.get("url") or "")[:60])

urls = [a.get("url"), b.get("url")]
if all(urls):
    print("剪辑合成中（拼接+转场+字幕+调色）…")
    out = call("/video/edit", "POST", {
        "clips": urls, "subtitles": ["第一幕", "第二幕", "成片"], "grade": "cinematic",
    }, timeout=600)
    print("剪辑结果:", json.dumps(out, ensure_ascii=False)[:250])
else:
    print("有片段生成失败，跳过剪辑")

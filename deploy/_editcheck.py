import json
import threading
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


results = {}
def gen(i, prompt):
    results[i] = call("/video", "POST", {"prompt": prompt})

print("生成 2 段视频片段（约 1-3 分钟）…")
t1 = threading.Thread(target=gen, args=(0, "海浪拍打礁石，日落，慢镜头"))
t2 = threading.Thread(target=gen, args=(1, "无人机飞越森林，晨雾，俯拍"))
t1.start(); t2.start(); t1.join(); t2.join()

urls = [results[0].get("url"), results[1].get("url")]
print("片段1:", (urls[0] or "")[:60])
print("片段2:", (urls[1] or "")[:60])

if all(urls):
    print("\n剪辑合成中（拼接+转场+字幕+调色）…")
    out = call("/video/edit", "POST", {
        "clips": urls,
        "subtitles": ["第一幕：海岸线", "第二幕：森林穿越", "合成完成"],
        "grade": "warm",
    }, timeout=500)
    print("剪辑结果:", json.dumps(out, ensure_ascii=False)[:300])
else:
    print("视频生成失败，无法测试剪辑：", results)

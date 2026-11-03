import os
from uuma.orbit_synthesis import OrbitCompactSynthesizer

os.environ["OPENAI_BASE_URL"] = "http://192.168.55.2:8080/v1"
os.environ["OPENAI_API_KEY"] = "ulk_GDET8pmQAcAO2WvhM7kKTSF-Bs6OJoJYO5gehBvgvf8"
os.environ["UUMA_KAG_LLM_MODEL"] = "gemini-3.8-flash"

snippets = [
    {
        "key": "S1",
        "title": "青葱气雾栽培缓苗期研究",
        "location": "试验结果",
        "text": "青葱分株后置于气雾培系统中，初期喷雾间隔为3分钟，通常需要5至7天恢复根系吸水能力并长出新根，进入正常生长状态。"
    }
]

res = OrbitCompactSynthesizer._generate("青葱分株后在气雾栽培下通常需要多少天缓苗？", snippets)
print("SUCCESS generating points:", res)

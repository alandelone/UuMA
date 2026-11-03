from uuma.orbit_synthesis import OrbitSynthesisModel

model = OrbitSynthesisModel(
    base_url="http://192.168.55.2:8080/v1",
    api_key="ulk_GDET8pmQAcAO2WvhM7kKTSF-Bs6OJoJYO5gehBvgvf8",
    model_name="gemini-3.8-flash"
)

points = model.synthesize("青葱分株后缓苗期大概需要多久？", [
    {"source_id": "src_1", "title": "青葱栽培技术", "text": "分株移栽后一般需要5-7天的缓苗期，待新根长出后恢复正常生长。"}
])
print("Synthesized points count:", len(points))
for p in points:
    print("Point:", p)

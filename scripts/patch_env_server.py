env_path = "/home/alandelone/.local/share/uuma/wisdom-forge-cutover-20261022/wisdom-production.env"
with open(env_path, "r", encoding="utf-8") as f:
    text = f.read()

text = text.replace("OPENAI_BASE_URL=http://127.0.0.1:8772/v1", "OPENAI_BASE_URL=http://192.168.55.2:8080/v1")
text = text.replace("OPENAI_API_KEY=JK0cso4cw4ChGqY-5s_RqBbHxOoFVnxy8mXGPOKjSMeZG05C", "OPENAI_API_KEY=ulk_GDET8pmQAcAO2WvhM7kKTSF-Bs6OJoJYO5gehBvgvf8")
text = text.replace("UUMA_KAG_LLM_MODEL=gemini-3.8-flash-medium", "UUMA_KAG_LLM_MODEL=gemini-3.8-flash")

with open(env_path, "w", encoding="utf-8") as f:
    f.write(text)
print("Successfully updated wisdom-production.env")

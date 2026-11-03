from pathlib import Path
from uuma.knowledge_service import KnowledgeService
from uuma.question_orbit import QuestionOrbitService
from uuma.knowledge_models import OrbitStatus
from uuma.wisdom_topics import TopicKnowledgeService

db_path = Path("/home/alandelone/.local/share/uuma/production/wisdom-oldman/wisdom.db")
knowledge = KnowledgeService(db_path)
topics = TopicKnowledgeService(knowledge)
orbits = QuestionOrbitService(knowledge, topics=topics)

orbit_id = "orbit_9ac4d099873b82f8f5a730cf07792419"
state = orbits.get(orbit_id)
current_status = state["orbit"]["status"]
print(f"Current orbit status: {current_status}")

res = orbits.transition(orbit_id, OrbitStatus.QUEUED, actor_id="orchestrator")
print("Transitioned orbit to QUEUED:")
print("New orbit status:", res["status"])
print("Stop reason:", res.get("stop_reason"))

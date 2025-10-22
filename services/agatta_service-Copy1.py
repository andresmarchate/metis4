from pymongo import MongoClient
from config import MONGO_URI, MONGO_DB_NAME, MONGO_TODOS_COLLECTION

client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
todos_collection = db[MONGO_TODOS_COLLECTION]

def get_agatta_stats(username):
    total_todos = todos_collection.count_documents({"username": username})
    completed_todos = todos_collection.count_documents({"username": username, "completed": True})
    return {
        "total_todos": total_todos,
        "completed": completed_todos
    }

def mark_task_completed(task_id):
    result = todos_collection.update_one(
        {"_id": task_id},
        {"$set": {"completed": True}}
    )
    if result.modified_count > 0:
        return {"success": True}
    return {"error": "Task not found"}

def get_agatta_todos(username):
    todos = todos_collection.find({"username": username})
    return list(todos)
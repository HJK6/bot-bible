from modules.Dynamo import Table
from modules.Config import PROJECTS_TABLE
from handlers.apigw import apigw_adapter


@apigw_adapter
def getProjectsHandler(event, context):
    """Get all projects, sorted by status (active first) then name."""
    table = Table(PROJECTS_TABLE)
    projects = table.get_all()
    status_order = {"active": 0, "paused": 1, "archived": 2}
    projects.sort(key=lambda p: (status_order.get(p.get("status", ""), 9), p.get("name", "")))
    return projects


@apigw_adapter
def getProjectHandler(event, context):
    """Get a single project by ID."""
    project_id = event.get("project_id", "")
    if not project_id:
        return {"code": 400, "status": "error", "message": "Missing project_id"}
    table = Table(PROJECTS_TABLE)
    project = table.get({"project_id": project_id})
    if not project:
        return {"code": 404, "status": "error", "message": "Project not found"}
    return project

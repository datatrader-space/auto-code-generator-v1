from .list_artifacts import ListArtifactsTool
from .get_artifact import GetArtifactTool

__all__ = ['ListArtifactsTool', 'GetArtifactTool']

def get_all_tools():
    return [ListArtifactsTool, GetArtifactTool]

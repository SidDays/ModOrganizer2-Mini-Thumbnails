import mobase

class ModThumbnailPlugin(mobase.IPlugin):
    def __init__(self):
        super().__init__()
        self._organizer: mobase.IOrganizer = None

    def init(self, organizer: mobase.IOrganizer) -> bool:
        self._organizer = organizer
        print("[ModThumbnail] Plugin initialized successfully.")
        return True

    def name(self) -> str:
        return "Mod Thumbnail Preview"

    def author(self) -> str:
        return "Local Dev"

    def description(self) -> str:
        return "Renders preview thumbnails in the mod list."

    def version(self) -> mobase.VersionInfo:
        return mobase.VersionInfo(1, 0, 0, mobase.ReleaseType.FINAL)

    def settings(self) -> list[mobase.PluginSetting]:
        return []

def createPlugin() -> mobase.IPlugin:
    return ModThumbnailPlugin()
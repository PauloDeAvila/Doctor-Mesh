"""Blender AI Mesh Doctor — non-destructive inspection and engineering records."""
bl_info = {
    "name": "AI Mesh Doctor", "author": "Mesh Doctor Project",
    "version": (0, 2, 0), "blender": (4, 2, 0),
    "location": "View3D > Sidebar > AI Mesh Doctor",
    "description": "Measured mesh inspection, explicit constraints and reusable evidence",
    "category": "Mesh",
}


def register():
    from . import ui
    ui.register()


def unregister():
    from . import ui
    ui.unregister()

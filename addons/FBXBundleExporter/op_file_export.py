import bpy, bmesh
import os
import mathutils
import math
import imp
import pathlib

from . import objects_organise

from . import modifiers
from . import platforms

imp.reload(modifiers)
imp.reload(platforms)


class op(bpy.types.Operator):
	bl_idname = "fbxbundle.file_export"
	bl_label = "export"
	bl_description = "Export selected bundles"

	@classmethod
	def poll(cls, context):

		if context.space_data.local_view:
			return False
		
		if len(bpy.context.selected_objects) == 0:
			return False

		if bpy.context.scene.FBXBundleSettings.path == "":
			return False

		if bpy.context.active_object and bpy.context.active_object.mode != 'OBJECT':
			return False

		if len( objects_organise.get_bundles() ) == 0:
			return False


		return True

	def execute(self, context):
		export(self, bpy.context.scene.FBXBundleSettings.target_platform)
		return {'FINISHED'}


prefix_copy = "EXPORT_ORG_"

def export(self, target_platform):

	# Warnings
	if bpy.context.scene.FBXBundleSettings.path == "":
		self.report({'ERROR_INVALID_INPUT'}, "Export path not set" )
		return

	folder = os.path.dirname( bpy.path.abspath( bpy.context.scene.FBXBundleSettings.path ))
	if not os.path.exists(folder):
		self.report({'ERROR_INVALID_INPUT'}, "Path doesn't exist" )
		return

	if len(bpy.context.selected_objects) == 0 and not bpy.context.view_layer.objects.active:
		self.report({'ERROR_INVALID_INPUT'}, "No objects selected" )
		return

	# Is Mode available?
	mode = bpy.context.scene.FBXBundleSettings.target_platform
	if mode not in platforms.platforms:
		self.report({'ERROR_INVALID_INPUT'}, "Platform '{}' not supported".format(mode) )
		return

	# Does the platform throw errors?
	if not platforms.platforms[mode].is_valid()[0]:
		self.report({'ERROR_INVALID_INPUT'}, platforms.platforms[mode].is_valid()[1] )
		return			


	# Store previous settings
	previous_selection = bpy.context.selected_objects.copy()
	previous_active = bpy.context.view_layer.objects.active
	previous_unit_system = bpy.context.scene.unit_settings.system
	previous_pivot = bpy.context.tool_settings.transform_pivot_point
	previous_cursor = bpy.context.scene.cursor.location.copy()

	if not bpy.context.view_layer.objects.active:
		bpy.context.view_layer.objects.active = bpy.context.selected_objects[0]

	bpy.ops.object.mode_set(mode='OBJECT')
	bundles = objects_organise.get_bundles()

	bpy.context.scene.unit_settings.system = 'METRIC'	
	bpy.context.tool_settings.transform_pivot_point = 'MEDIAN_POINT'

	objects_organise.recent_store(bundles)

	for name,objects in bundles.items():
		pivot = objects_organise.get_pivot(objects).copy()

		# Detect if animation export...
		use_animation = objects_organise.get_objects_animation(objects)

		parent_dict = {}
		for obj in objects:
			if (obj.parent is not None):
				parent_dict[obj.name] = obj.parent.name
			else:
				parent_dict[obj.name] = None
				
		copies = []
		for obj in objects:
			name_original = obj.name
			obj.name = prefix_copy+name_original

			bpy.ops.object.select_all(action="DESELECT")
			obj.select_set(state = True)
			bpy.context.view_layer.objects.active = obj
			obj.hide_viewport = False
			
			# Copy
			bpy.ops.object.duplicate()
			bpy.ops.object.convert(target='MESH')
			bpy.context.object.name = name_original
			copies.append(bpy.context.object)
			# bpy.context.object.location-= pivot

		# Parent hierarchy
		for copy_name, parent_name in parent_dict.items():
			if (parent_dict[copy_name] != None):
				if (copy_name != parent_name):
					bpy.ops.object.select_all(action="DESELECT")
					child_object = bpy.data.objects[copy_name]
					parent_object = bpy.data.objects[parent_name]
					child_object.select_set(True)
					parent_object.select_set(True)
					bpy.context.view_layer.objects.active = parent_object
					bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)

		# apply rotation and scale
		# find roots
		roots = []
		
		for obj in copies:
			root = obj
			for i in range(1000):
				if root.parent:
					root = root.parent
				else:
					if (root not in roots):
						roots.append(root)

		for copy in copies:
			bpy.ops.object.select_all(action="DESELECT")
			copy.select_set(True)			
			bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

		# unity rx -90, apply, rx 90 to get clean transforms
		if bpy.context.scene.FBXBundleSettings.target_platform == 'UNITY':
			bpy.ops.object.select_all(action="DESELECT")
			for root in roots: 
				root.select_set(True)
				root.rotation_euler[0] = -1.5708
			for copy in copies: copy.select_set(True)		
			bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
			for root in roots: root.rotation_euler[0] = 1.5708

		bpy.ops.object.select_all(action="DESELECT")
		for obj in copies:
			obj.select_set(state = True)
		bpy.context.view_layer.objects.active = copies[0]
		

		# Apply modifiers

		# full = self.process_path(name, path)+"{}".format(os.path.sep)+platforms.platforms[mode].get_filename( self.process_name(name) )  		
		 # os.path.join(folder, name)+"."+platforms.platforms[mode].extension
		path_folder = folder
		path_name = name
		for modifier in modifiers.modifiers:
			if modifier.get("active"):
				copies = modifier.process_objects(name, copies)
				path_folder = modifier.process_path(path_name, path_folder)
				path_name = modifier.process_name(path_name)

		path_full = os.path.join(path_folder, path_name)+"."+platforms.platforms[mode].extension
		
		# Create path if not yet available
		directory = os.path.dirname(path_full)
		pathlib.Path(directory).mkdir(parents=True, exist_ok=True)

		# Select all copies
		bpy.ops.object.select_all(action="DESELECT")
		for obj in copies:
			obj.select_set(state = True)

		# Export per platform (Unreal, Unity, ...)
		print("Export {}x = {}".format(len(objects),path_full))
		platforms.platforms[mode].file_export(path_full)

		# Delete copies
		bpy.ops.object.delete()
		copies.clear()
		
		# Restore names
		for obj in objects:
			obj.name = obj.name.replace(prefix_copy,"")

		


	# Restore previous settings
	bpy.context.scene.unit_settings.system = previous_unit_system
	bpy.context.tool_settings.transform_pivot_point = previous_pivot
	bpy.context.scene.cursor.location = previous_cursor
	bpy.context.view_layer.objects.active = previous_active
	bpy.ops.object.select_all(action='DESELECT')
	for obj in previous_selection:
		obj.select_set(state = True)

	if bpy.context.scene.FBXBundleSettings.mode_bundle == 'MATERIAL':
		bpy.ops.ed.undo()

	# Show popup
	
	def draw(self, context):
		filenames = []
		# Get bundle file names
		for name,objects in bundles.items():
			for modifier in modifiers.modifiers:
				if modifier.get("active"):
					name = modifier.process_name(name)	
			filenames.append(name+"."+platforms.platforms[mode].extension)

		self.layout.label(text="Exported {}".format(", ".join(filenames)))

	bpy.context.window_manager.popup_menu(draw, title = "Exported {}x files".format(len(bundles)), icon = 'INFO')
	
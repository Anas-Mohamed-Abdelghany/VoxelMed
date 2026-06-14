"""
vtk_renderer.py
---------------
Mixin that owns the 3-D volume rendering logic using VTK.
"""

import numpy as np
import vtkmodules.all as vtk
from vtkmodules.util import numpy_support


class VTKRendererMixin:
    def render_3d_volume(self):
        if self.image_array is None:
            return

        # Clear existing actors
        self.renderer.RemoveAllViewProps()

        # Build VTK image data from NumPy array
        vtk_image = vtk.vtkImageData()
        vtk_image.SetDimensions(self.image_array.shape[::-1])
        vtk_image.AllocateScalars(vtk.VTK_UNSIGNED_CHAR, 1)

        # Flip to match VTK coordinate system
        flipped_array = np.flip(self.image_array, axis=0)
        vtk_array = numpy_support.numpy_to_vtk(
            flipped_array.ravel(), deep=True, array_type=vtk.VTK_UNSIGNED_CHAR
        )
        vtk_image.GetPointData().SetScalars(vtk_array)

        # Volume mapper
        volume_mapper = vtk.vtkSmartVolumeMapper()
        volume_mapper.SetInputData(vtk_image)

        # Volume property
        volume_property = vtk.vtkVolumeProperty()
        volume_property.ShadeOn()
        volume_property.SetInterpolationTypeToLinear()

        # Color transfer function
        ctf = vtk.vtkColorTransferFunction()
        ctf.AddRGBPoint(0,   0.0, 0.0, 0.0)
        ctf.AddRGBPoint(128, 0.5, 0.5, 0.5)
        ctf.AddRGBPoint(255, 1.0, 1.0, 1.0)
        volume_property.SetColor(ctf)

        # Opacity transfer function
        otf = vtk.vtkPiecewiseFunction()
        otf.AddPoint(0,   0.0)
        otf.AddPoint(128, 0.5)
        otf.AddPoint(255, 1.0)
        volume_property.SetScalarOpacity(otf)

        # Assemble volume actor
        volume = vtk.vtkVolume()
        volume.SetMapper(volume_mapper)
        volume.SetProperty(volume_property)

        self.renderer.AddVolume(volume)
        self.renderer.ResetCamera()
        self.vtk_widget.GetRenderWindow().Render()

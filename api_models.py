"""
Pydantic models for Hunyuan3D API server.
"""
from typing import Optional, Literal
from pydantic import BaseModel, Field


class ImageSelection(BaseModel):
    """User-selected image region for object-focused generation."""
    box: Optional[list[float]] = Field(
        None,
        description="Selected bounding box [x1, y1, x2, y2].",
        min_length=4,
        max_length=4,
        example=[120, 80, 720, 880]
    )
    box_format: Literal["normalized_1000", "normalized", "pixel"] = Field(
        "normalized_1000",
        description="Coordinate format for box: normalized_1000 (0-1000), normalized (0-1), or pixel."
    )
    mask: Optional[str] = Field(
        None,
        description="Optional base64 grayscale/RGBA mask. White/alpha selects the object."
    )
    mask_threshold: int = Field(
        8,
        description="Mask threshold from 0-255.",
        ge=0,
        le=255
    )
    mask_feather: int = Field(
        1,
        description="Soft edge radius in pixels applied to the mask.",
        ge=0,
        le=32
    )
    invert_mask: bool = Field(
        False,
        description="Invert the mask before applying it."
    )
    padding: int = Field(
        24,
        description="Padding in pixels around the selected region when cropping.",
        ge=0,
        le=512
    )
    crop: bool = Field(
        True,
        description="Crop the output image around the selected object."
    )
    transparent_outside_box: bool = Field(
        False,
        description="When no mask is supplied, make pixels outside the box transparent instead of only cropping."
    )


class GenerationRequest(BaseModel):
    """Request model for 3D generation API"""
    image: str = Field(
        ..., 
        description="Base64 encoded input image for 3D generation",
        example="iVBORw0KGgoAAAANSUhEUgAAAAQAAAAECAIAAAAmkwkpAAAAEElEQVR4nGP8z4AATAxEcQAz0QEHOoQ+uAAAAABJRU5ErkJggg=="
    )
    remove_background: bool = Field(
        True,
        description="Whether to automatically remove background from input image"
    )
    selection: Optional[ImageSelection] = Field(
        None,
        description="Optional user-selected object box/mask to isolate before 3D generation."
    )
    texture: bool = Field(
        False,
        description="Whether to generate textures for the 3D model"
    )
    seed: int = Field(
        1234,
        description="Random seed for reproducible generation",
        ge=0,
        le=2**32-1
    )
    octree_resolution: int = Field(
        256,
        description="Resolution of the octree for mesh generation",
        ge=64,
        le=512
    )
    num_inference_steps: int = Field(
        5,
        description="Number of inference steps for generation",
        ge=1,
        le=20
    )
    guidance_scale: float = Field(
        5.0,
        description="Guidance scale for generation",
        ge=0.1,
        le=20.0
    )
    num_chunks: int = Field(
        8000,
        description="Number of chunks for processing",
        ge=1000,
        le=20000
    )
    face_count: int = Field(
        40000,
        description="Maximum number of faces for texture generation",
        ge=1000,
        le=100000
    )


class GenerationResponse(BaseModel):
    """Response model for generation status"""
    uid: str = Field(..., description="Unique identifier for the generation task")


class StatusResponse(BaseModel):
    """Response model for status endpoint"""
    status: str = Field(..., description="Status of the generation task")
    model_base64: Optional[str] = Field(
        None, 
        description="Base64 encoded generated model file (only when status is 'completed')"
    )
    message: Optional[str] = Field(
        None,
        description="Error message (only when status is 'error')"
    )


class HealthResponse(BaseModel):
    """Response model for health check"""
    status: str = Field(..., description="Health status")
    worker_id: str = Field(..., description="Worker identifier") 


class SelectionPreviewRequest(BaseModel):
    """Request model for previewing the selected object crop."""
    image: str = Field(..., description="Base64 encoded source image")
    selection: ImageSelection = Field(..., description="User-selected object region")


class SelectionPreviewResponse(BaseModel):
    """Response model containing selected object preview image."""
    image: str = Field(..., description="Base64 encoded PNG after applying the selection")

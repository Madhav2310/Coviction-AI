"""

Media router — serves uploaded images by observation ID.

Simple local filesystem storage. Swap with S3 when scaling.

"""

import os

from uuid import UUID



from fastapi import APIRouter, HTTPException

from fastapi.responses import FileResponse



router = APIRouter(prefix="/media", tags=["media"])



UPLOADS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")





@router.get("/{obs_id}")

async def get_media(obs_id: UUID):

    """Serve the image file for a given observation ID."""

    # Look for any file matching the obs_id (regardless of extension)

    if not os.path.isdir(UPLOADS_DIR):

        raise HTTPException(status_code=404, detail="No uploads directory")



    for fname in os.listdir(UPLOADS_DIR):

        if fname.startswith(str(obs_id)):

            filepath = os.path.join(UPLOADS_DIR, fname)

            # Determine media type from extension

            ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "bin"

            media_types = {

                "jpg": "image/jpeg", "jpeg": "image/jpeg",

                "png": "image/png", "gif": "image/gif",

                "webp": "image/webp", "heic": "image/heic",

            }

            media_type = media_types.get(ext, "application/octet-stream")

            return FileResponse(filepath, media_type=media_type)



    raise HTTPException(status_code=404, detail="Image not found")

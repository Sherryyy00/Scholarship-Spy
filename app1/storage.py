"""
Profile photos on Cloudinary, so they survive restarts on hosts with a temporary disk.

Used only when CLOUDINARY_URL is set (cloudinary://<key>:<secret>@<cloud-name>);
otherwise photos are saved on local disk as before. Photos are already checked and
re-encoded (app1/uploads.py) before they get here.
"""

import posixpath
import uuid

import cloudinary
import cloudinary.uploader
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible

FOLDER = "scholarship-spy"


@deconstructible
class CloudinaryMediaStorage(Storage):
    def _public_id(self, name):
        return f"{FOLDER}/{posixpath.splitext(name)[0]}"

    def _save(self, name, content):
        directory = posixpath.dirname(name)
        name = posixpath.join(directory, uuid.uuid4().hex + ".jpg")
        content.seek(0)
        cloudinary.uploader.upload(
            content, public_id=self._public_id(name), resource_type="image",
            overwrite=False, invalidate=True,
        )
        return name

    def url(self, name):
        return cloudinary.CloudinaryImage(self._public_id(name)).build_url(
            secure=True, fetch_format="auto", quality="auto")

    def delete(self, name):
        cloudinary.uploader.destroy(self._public_id(name), resource_type="image", invalidate=True)

    def exists(self, name):
        return False  # every upload gets a fresh random name

    def size(self, name):
        raise NotImplementedError("Size isn't tracked for Cloudinary photos.")

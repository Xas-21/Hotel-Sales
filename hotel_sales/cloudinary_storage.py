from cloudinary_storage.storage import MediaCloudinaryStorage
from django.conf import settings
import cloudinary


class PublicMediaCloudinaryStorage(MediaCloudinaryStorage):
    """
    Custom Cloudinary storage that ensures files are publicly accessible
    """
    
    def __init__(self, **settings_dict):
        super().__init__(**settings_dict)
        # Configure Cloudinary to make files publicly accessible
        cloudinary.config(
            cloud_name=settings.CLOUDINARY_STORAGE['CLOUD_NAME'],
            api_key=settings.CLOUDINARY_STORAGE['API_KEY'],
            api_secret=settings.CLOUDINARY_STORAGE['API_SECRET'],
            secure=True
        )
    
    def _save(self, name, content):
        """
        Override save to ensure files are uploaded as public
        """
        # Upload with public access
        result = cloudinary.uploader.upload(
            content,
            public_id=name,
            resource_type="auto",
            folder="media",
            use_filename=True,
            unique_filename=True,
            overwrite=True,
            invalidate=True
        )
        
        # Return the public URL
        return result['public_id']
    
    def url(self, name):
        """
        Return the public URL for the file
        """
        if not name:
            return None
        
        # Build the public URL
        return cloudinary.CloudinaryResource(name).build_url(
            resource_type="auto",
            secure=True
        )

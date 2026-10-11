import io
from pathlib import Path
from PIL import Image
from pypdf import PdfReader
from fastapi import HTTPException
from app.core.config import settings

MAX_BYTES = 15 * 1024 * 1024

def file_path(document_id):
    from uuid import UUID
    identifier = str(UUID(str(document_id)))
    return settings.storage_dir / (identifier + '.bin')

def validate_file(data, content_type):
    if not data:
        raise HTTPException(400, 'File is empty')
    try:
        if data.startswith(b'%PDF-'):
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted or not 1 <= len(reader.pages) <= 100:
                raise ValueError('PDF must be unencrypted and contain 1–100 pages')
            actual = 'application/pdf'
        else:
            with Image.open(io.BytesIO(data)) as image:
                if image.format not in ('JPEG', 'PNG'):
                    raise ValueError('Only PDF, JPEG and PNG are supported')
                actual = 'image/jpeg' if image.format == 'JPEG' else 'image/png'
                image.verify()
        if content_type not in (actual, 'image/jpg' if actual == 'image/jpeg' else actual):
            raise ValueError('File content does not match the declared type')
        return actual
    except Exception as exc:
        raise HTTPException(400, 'Invalid or unsupported document file') from exc

async def read_upload(upload):
    data = bytearray()
    while part := await upload.read(64 * 1024):
        data.extend(part)
        if len(data) > MAX_BYTES:
            raise HTTPException(413, 'File exceeds 15 MB')
    return bytes(data)

def safe_name(filename):
    name = Path((filename or 'document').replace('\\', '/')).name
    return ''.join(c for c in name if c.isprintable() and c not in '\"<>').strip()[:200] or 'document'

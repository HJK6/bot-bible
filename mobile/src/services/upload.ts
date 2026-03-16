import { callApi } from './api';

interface UploadUrlResponse {
  upload_url: string;
  object_url: string;
  key: string;
}

export async function uploadImage(
  imageUri: string,
  agentId: string = 'general'
): Promise<string> {
  // Get presigned URL from backend
  const { upload_url, object_url } = await callApi<UploadUrlResponse>(
    'dashGetUploadUrl',
    {
      agent_id: agentId,
      content_type: 'image/jpeg',
      file_ext: 'jpg',
    }
  );

  // Fetch the local image as blob
  const response = await fetch(imageUri);
  if (!response.ok) {
    throw new Error('Failed to load selected image');
  }
  const blob = await response.blob();

  // Upload to S3 via presigned URL
  const s3Response = await fetch(upload_url, {
    method: 'PUT',
    headers: { 'Content-Type': 'image/jpeg' },
    body: blob,
  });
  if (!s3Response.ok) {
    throw new Error('Failed to upload image');
  }

  return object_url;
}

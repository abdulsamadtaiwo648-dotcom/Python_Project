/* Resize a photo on the device before it is uploaded.
   Keeps the longest side under MAX_SIDE pixels and re-encodes as WebP (or
   JPEG where WebP is not supported). Falls back to the original file if the
   browser cannot decode it, so an unusual format still uploads. */
(function () {
    const MAX_SIDE = 1600;
    const SKIP_UNDER_BYTES = 350 * 1024;

    function encode(canvas, type, quality) {
        return new Promise(resolve => canvas.toBlob(resolve, type, quality));
    }

    async function shrinkImage(file) {
        if (!file || !file.type.startsWith('image/')) return file;
        let bitmap;
        try {
            bitmap = await createImageBitmap(file);
        } catch (_) {
            return file;
        }
        const scale = Math.min(1, MAX_SIDE / Math.max(bitmap.width, bitmap.height));
        if (scale === 1 && file.size <= SKIP_UNDER_BYTES) {
            bitmap.close();
            return file;
        }
        const canvas = document.createElement('canvas');
        canvas.width = Math.round(bitmap.width * scale);
        canvas.height = Math.round(bitmap.height * scale);
        const context = canvas.getContext('2d');
        context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        bitmap.close();

        let blob = await encode(canvas, 'image/webp', 0.85);
        if (!blob || blob.type !== 'image/webp') blob = await encode(canvas, 'image/jpeg', 0.85);
        if (!blob || blob.size >= file.size) return file;
        const extension = blob.type === 'image/webp' ? 'webp' : 'jpg';
        const base = (file.name || 'photo').replace(/\.[^.]+$/, '');
        return new File([blob], `${base}.${extension}`, { type: blob.type });
    }

    window.shrinkImage = shrinkImage;
})();

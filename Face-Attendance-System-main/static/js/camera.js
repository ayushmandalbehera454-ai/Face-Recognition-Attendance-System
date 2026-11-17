/* Tiny webcam helper. getUserMedia needs https:// or http://localhost */
class Camera {
  constructor(video) { this.video = video; this.stream = null; this.canvas = document.createElement('canvas'); }
  get active() { return !!this.stream; }
  async start() {
    if (!navigator.mediaDevices?.getUserMedia) throw new Error('This browser cannot use the camera. Use Chrome, Edge or Firefox on https or localhost.');
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }, audio: false });
    } catch (e) {
      throw new Error(e.name === 'NotAllowedError' ? 'Camera permission was blocked. Allow it in the browser address bar.' : 'No camera found or it is in use by another app.');
    }
    this.video.srcObject = this.stream;
    await this.video.play();
    return { w: this.video.videoWidth, h: this.video.videoHeight };
  }
  stop() {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null; this.video.srcObject = null;
  }
  capture(maxWidth = 480, quality = 0.8) {
    const vw = this.video.videoWidth, vh = this.video.videoHeight;
    if (!vw) return null;
    const scale = Math.min(1, maxWidth / vw);
    this.canvas.width = Math.round(vw * scale); this.canvas.height = Math.round(vh * scale);
    this.canvas.getContext('2d').drawImage(this.video, 0, 0, this.canvas.width, this.canvas.height);
    return this.canvas.toDataURL('image/jpeg', quality);
  }
}

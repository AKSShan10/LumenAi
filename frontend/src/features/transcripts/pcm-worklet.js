// Runs inside the browser's audio thread (an AudioWorklet). It turns the microphone sound into what the
// speech-to-text service expects: 16 kHz, 16-bit, one channel. Every 0.1 second it hands one piece to MicToText.jsx,
// which sends it over the WebSocket. Nothing is saved here or anywhere else.
const TARGET_RATE = 16000;
const PIECE = TARGET_RATE / 10;               // 0.1 second = 1600 samples

class PcmSender extends AudioWorkletProcessor {
  constructor() {
    super();
    this.step = sampleRate / TARGET_RATE;     // e.g. 48000 / 16000 = 3: keep every 3rd sample
    this.position = 0;
    this.piece = new Int16Array(PIECE);
    this.filled = 0;
  }

  // Called by the browser for every 128 samples of microphone sound
  process(inputs) {
    const sound = inputs[0] && inputs[0][0];   // the first channel of the microphone
    if (!sound) return true;
    for (; this.position < sound.length; this.position += this.step) {
      const value = Math.max(-1, Math.min(1, sound[Math.floor(this.position)]));
      this.piece[this.filled++] = value < 0 ? value * 0x8000 : value * 0x7fff;   // -1..1 → 16-bit number
      if (this.filled === PIECE) {
        this.port.postMessage(this.piece.buffer, [this.piece.buffer]);     // hand it over (no copy)
        this.piece = new Int16Array(PIECE);
        this.filled = 0;
      }
    }
    this.position -= sound.length;
    return true;                                // keep running
  }
}

registerProcessor("pcm-sender", PcmSender);

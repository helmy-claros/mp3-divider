"""Run the four-stem Hybrid Demucs model with bounded working memory."""
import sys
from contextlib import ExitStack
from pathlib import Path

import soundfile as sf
import torch
from torchaudio.pipelines import HDEMUCS_HIGH_MUSDB_PLUS


@torch.inference_mode()
def separate(source, folder):
    torch.set_num_threads(min(4, torch.get_num_threads()))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = HDEMUCS_HIGH_MUSDB_PLUS.get_model().to(device)
    rate = HDEMUCS_HIGH_MUSDB_PLUS.sample_rate
    block, context = 6 * rate, rate
    folder.mkdir(parents=True, exist_ok=True)
    with sf.SoundFile(source) as audio, ExitStack() as stack:
        outputs = [stack.enter_context(sf.SoundFile(folder / (name + ".wav"), "w", rate, 2, subtype="FLOAT")) for name in model.sources]
        for start in range(0, len(audio), block):
            left = max(start - context, 0)
            audio.seek(left)
            frames = audio.read(start + block + context - left, dtype="float32")
            signal = torch.from_numpy(frames.T.copy()).to(device)
            reference = signal.mean(0)
            mean, scale = reference.mean(), reference.std(unbiased=False).clamp_min(1e-6)
            estimates = model(((signal - mean) / scale).unsqueeze(0))[0] * scale + mean
            count = min(block, len(audio) - start)
            for output, estimate in zip(outputs, estimates):
                output.write(estimate[:, start-left:start-left+count].T.cpu().numpy())


if __name__ == "__main__":
    separate(Path(sys.argv[1]), Path(sys.argv[2]))

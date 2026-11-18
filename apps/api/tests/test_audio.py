from app.services import audio


def test_find_binary_falls_back_to_winget_location(tmp_path, monkeypatch):
    """Terminal lama tanpa ffmpeg di PATH tetap bisa menemukan ffmpeg hasil winget."""
    exe = tmp_path / "Microsoft/WinGet/Packages/Gyan.FFmpeg_x/ffmpeg-9-full_build/bin/ffmpeg.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(audio.shutil, "which", lambda _: None)
    audio.find_binary.cache_clear()
    try:
        assert audio.find_binary("ffmpeg") == str(exe)
        assert audio.find_binary("tidak-ada") == "tidak-ada"
    finally:
        audio.find_binary.cache_clear()

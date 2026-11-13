"""Audio-file STT follows profile opt-in and preserves pending-message single execution."""
from types import SimpleNamespace

from gateway.platforms.event import MessageType
from gateway.run import GatewayRunner, _event_media_is_stt_input, _profile_runtime_scope


def test_audio_file_stt_is_scoped_to_current_profile(tmp_path):
    homes = []
    for name, enabled in [('off', False), ('on', True)]:
        home = tmp_path / name
        home.mkdir()
        (home / 'config.yaml').write_text(
            f'stt:\n  transcribe_audio_files: {str(enabled).lower()}\n', encoding='utf-8'
        )
        homes.append(home)
    for home, expected in [(homes[0], False), (homes[1], True), (homes[0], False)]:
        with _profile_runtime_scope(home, {}):
            for kind in (MessageType.AUDIO, MessageType.DOCUMENT):
                event = SimpleNamespace(
                    message_type=kind, media_urls=['/cache/a.ogg', '/cache/b.pdf'],
                    media_types=['audio/ogg', 'application/pdf'],
                )
                assert _event_media_is_stt_input(event, 0) is expected
                assert _event_media_is_stt_input(event, 1) is False
                images, voices, files, videos = GatewayRunner._classify_inbound_media(event, False)
                assert voices == (['/cache/a.ogg'] if expected else [])
                assert files == ([] if expected else ['/cache/a.ogg'])


def test_pending_audio_file_uses_same_single_transcription_path(tmp_path):
    (tmp_path / 'config.yaml').write_text('stt:\n  transcribe_audio_files: true\n')
    event = SimpleNamespace(
        message_type=MessageType.AUDIO, media_urls=['/cache/a.ogg'], media_types=['audio/ogg']
    )
    runner = object.__new__(GatewayRunner)
    with _profile_runtime_scope(tmp_path, {}):
        assert runner._pending_event_audio_paths(event) == ['/cache/a.ogg']
        assert runner._classify_inbound_media(event, False)[1] == ['/cache/a.ogg']
        assert runner._classify_inbound_media(event, True)[1:3] == ([], [])

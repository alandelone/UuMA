import sys
import threading
from types import ModuleType, SimpleNamespace

from uuma import kag_bridge


def test_onnx_embedding_bounds_batches_and_preserves_order_and_scalar_shape(monkeypatch):
    class Tensor(list):
        def astype(self, kind, copy):
            assert kind == "int64" and copy is False
            return self

    numpy = SimpleNamespace(
        int64="int64", float32="float32", empty=lambda shape, dtype: [],
        concatenate=lambda parts, axis: [row for part in parts for row in part],
    )
    monkeypatch.setitem(sys.modules, "numpy", numpy)
    encoder = object.__new__(kag_bridge._OnnxBGEM3Encoder)
    encoder._max_length = 2048
    encoder._batch_size = 1
    encoder._encode_lock = threading.Lock()
    seen = []

    def tokenize(texts, **options):
        seen.append((texts, options))
        values = Tensor([[int(text)] for text in texts])
        return {"input_ids": values, "attention_mask": Tensor([[1] for _ in texts])}

    class Session:
        def run(self, outputs, inputs):
            assert outputs == ["sentence_embedding"]
            assert len(inputs["input_ids"]) == 1
            return [[[row[0]] * 1024 for row in inputs["input_ids"]]]

    encoder._tokenizer = tokenize
    encoder._session = Session()
    vectors = encoder.encode(["3", "1", "2"])["dense_vecs"]
    assert len(vectors) == 3 and all(len(row) == 1024 for row in vectors)
    assert [row[0] for row in vectors] == [3, 1, 2]
    assert all(options["max_length"] == 2048 for _, options in seen)
    assert len(encoder.encode("4")["dense_vecs"]) == 1024
    assert encoder.encode([])["dense_vecs"] == []


def test_kag_executors_share_one_onnx_model_per_path(tmp_path, monkeypatch):
    module = ModuleType("kag.common.vectorize_model.local_bge_model")

    class Model:
        pass

    module.LocalBGEM3VectorizeModel = Model
    monkeypatch.setitem(sys.modules, module.__name__, module)
    model_path = tmp_path / "model"
    (model_path / "onnx").mkdir(parents=True)
    (model_path / "onnx/model.onnx").touch()
    monkeypatch.setenv("UUMA_BGE_M3_PATH", str(model_path))
    monkeypatch.setenv("UUMA_BGE_BACKEND", "onnx")
    loaded = []

    def load(path):
        loaded.append(path)
        return object()

    monkeypatch.setattr(kag_bridge, "_OnnxBGEM3Encoder", load)
    monkeypatch.setattr(kag_bridge, "_bge_runtime", {})
    kag_bridge._configure_local_bge_runtime()
    first = Model()._load_model(str(model_path))
    assert Model()._load_model(str(model_path / ".")) is first
    assert len(loaded) == 1
    assert kag_bridge._bge_runtime["batch_size"] == 1

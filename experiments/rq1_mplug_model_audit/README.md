# mPLUG-Owl2 Checkpoint Compatibility Audit

## Question

The call20 and call100 logs reported that 12 visual-abstractor q/k positional
embedding tensors were "newly initialized." This audit determines whether they
are missing trained weights that invalidate the evaluation.

## Evidence

The warning names:

```text
model.visual_abstractor.encoder.layers.[0-5].
crossattention.attention.{q_pos_embed,k_pos_embed}
```

The local checkpoint index contains none of these 12 keys.

That absence matches the upstream conversion implementation:

- `convert_mplug_owl2_weight_to_hf.py` explicitly comments out both keys;
- `visual_encoder.py` constructs both tensors from deterministic sinusoidal
  position-embedding functions;
- they are registered as buffers, not trainable parameters.

Runtime inspection of one abstractor attention layer produced:

```text
parameters []
buffers [
  ('q_pos_embed', (64, 1024), False),
  ('k_pos_embed', (1025, 1024), False)
]
```

`False` is the `requires_grad` value. The tensors are included in the module
state dict because `register_buffer()` is persistent by default, which causes
newer Transformers loading code to report their absence from the checkpoint.

## Conclusion

The warning does not indicate randomly initialized trained visual weights.
These are fixed sinusoidal buffers intentionally omitted by the official
conversion script and reconstructed by model code. The call20 and call100
results do not need to be discarded for this reason.

The exact wording of the Transformers warning is misleading in this case.
Future reports should call it a deterministic-buffer compatibility warning,
not a missing-weight warning.

## Environment

- Python: 3.10.11
- PyTorch: 2.3.1+cu121
- Transformers: 4.45.2
- Accelerate: 0.34.2
- bitsandbytes: 0.49.2
- mPLUG repository commit: `0f3068fdb47b77aedc71fc39f5735cd7aa35e8f9`
- local compatibility diff hash: `2fe335b0f89f12a4e78a70cd5d1bd9f89343a882`
- model config SHA-256:
  `36426f5b5a9bfd44326128284b7660d81a5233b9abb7c15611f0d96fea92c176`
- checkpoint index SHA-256:
  `f48d5bb04d4c0543c985281e84c15f7b88cf6a1f232bc601caf736acc6e6572a`

The nested mPLUG repository has pre-existing local compatibility edits in
`builder.py`, `configuration_mplug_owl2.py`, `modeling_llama2.py`, and
`visual_encoder.py`. This audit did not modify, revert, or commit them.

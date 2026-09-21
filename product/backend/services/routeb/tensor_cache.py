"""Move unregistered tensor caches as well as nn.Module weights and buffers."""


def move_model_and_caches(model, device):
    import torch
    model.to(device)
    memo = {}

    def move(value):
        identity = id(value)
        if identity in memo:
            return memo[identity]
        if isinstance(value, torch.Tensor):
            result = value.to(device)
            memo[identity] = result
            return result
        if isinstance(value, dict):
            memo[identity] = value
            for key in list(value):
                value[key] = move(value[key])
        elif isinstance(value, list):
            memo[identity] = value
            for index, item in enumerate(value):
                value[index] = move(item)
        elif isinstance(value, tuple):
            memo[identity] = value
            # Preserve named tuples used by model implementations.
            items = [move(item) for item in value]
            if all(a is b for a, b in zip(items, value)):
                return value
            result = type(value)(*items) if hasattr(value, "_fields") else type(value)(items)
            memo[identity] = result
            return result
        return value

    for module in model.modules():
        for name, value in list(vars(module).items()):
            if name not in ("_parameters", "_buffers", "_modules"):
                # .to() already handles registered tensors. Also move plain
                # reference-feature / attention caches in tensor containers.
                if isinstance(value, (torch.Tensor, dict, list, tuple)):
                    setattr(module, name, move(value))

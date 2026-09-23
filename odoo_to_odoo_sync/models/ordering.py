def strongly_connected(nodes, edges):
    index = {}
    low = {}
    on_stack = set()
    stack = []
    components = []
    counter = 0
    for root in sorted(nodes):
        if root in index:
            continue
        work = [(root, iter(sorted(edges[root])))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, children = work[-1]
            advanced = False
            for child in children:
                if child not in index:
                    index[child] = low[child] = counter
                    counter += 1
                    stack.append(child)
                    on_stack.add(child)
                    work.append((child, iter(sorted(edges[child]))))
                    advanced = True
                    break
                if child in on_stack:
                    low[node] = min(low[node], index[child])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                components.append(component)
    return components


def dependency_order(depends, required):
    ordered = []
    for component in strongly_connected(set(depends), depends):
        remaining = set(component)
        while remaining:
            ready = sorted(name for name in remaining if not required[name] & remaining)
            if not ready:
                ready = [min(remaining, key=lambda name: (len(required[name] & remaining), name))]
            ready.sort(key=lambda name: (len(depends[name] & remaining), name))
            first = ready[0]
            ordered.append(first)
            remaining.discard(first)
    return ordered

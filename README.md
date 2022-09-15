# Remove Empty Namespaces Operator
A Kubernetes operator that deletes namespaces without resources.

## Description

Operator iterates over all namespaced api-resources in every namespace. If there are no resources, it annotates namespace as a candidate for deletion. The namespace will be deleted after specified time interval if there will be no resources still.

So operator doesn't delete namespace instantly: first time it marks namespace and after `interval` operator deletes ns if it's still empty.
## Installation

```
kubectl apply -k .
```

## Configuration

See `settings.yaml` as example

```yaml
interval: "18000"  # 5h
initialDelay: "300"  # 5m
ignoredResouces:
  - apiGroup: ""
    kind: ConfigMap
    nameRegExp: kube-root-ca.crt
  - apiGroup: ""
    kind: ConfigMap
    nameRegExp: werf-synchronization
  - apiGroup: ""
    kind: Secret
    nameRegExp: default-token-\w+$
  - apiGroup: ""
    kind: ServiceAccount
    nameRegExp: default
protectedNamespaces:
  - protected-one
  - default
  - kube-public
  - kube-system
```

* `interval` - interval between namespaces check
* `initialDelay` - 'grace period' before new namespace will be checked
* `ignoredResouces` - namespace will be treated as empty if it contains only 'ignored resources'
* `protectedNamespaces` - these namespaces will not be deleated dispite of emptiness

Note that usually there is no need to add kubernetes default namespaces (`default`, `kube-public` and `kube-system`) to `protectedNamespaces` because they have some resources inside in the most cases. But you certainly can do it just to be sure that nothing will happen with them. Also, if your `kube-system` is empty you are probably it trouble already :)

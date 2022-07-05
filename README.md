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

See `settings.yaml`

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
```

* `interval` - interval between namespaces check
* `initialDelay` - 'grace period' before new namespace will be checked
* `ignoredResouces` - namespace will be treated as empty if it contains only 'ignored resources'

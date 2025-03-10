# Remove Empty Namespaces Operator

A Kubernetes operator that deletes namespaces without resources.

## Description

Operator iterates over all namespaced api-resources in every namespace. If there are no resources, it annotates namespace as a candidate for deletion. The namespace will be deleted after specified time interval if there will be no resources still.

So operator doesn't delete namespace instantly: first time it marks namespace and after `interval` operator deletes ns if it's still empty.

## Installation

```shell
helm repo add remove-empty-ns-operator https://rgeraskin.github.io/remove-empty-ns-operator/
helm upgrade --install --create-namespace -n remove-empty-ns-operator remove-empty-ns-operator/remove-empty-ns-operator
```

## Configuration

See `settings` in `helm/values.yaml` as example

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
  - default
  - kube-public
  - kube-system
cleanupFinalizers: true
```

* `interval` - interval between namespaces check
* `initialDelay` - 'grace period' before new namespace will be checked
* `ignoredResouces` - namespace will be treated as empty if it contains only 'ignored resources'
* `protectedNamespaces` - these namespaces will not be deleated dispite of emptiness

  Usually there is no need to add kubernetes default namespaces (`default`, `kube-public`, and `kube-system`) to `protectedNamespaces` because they have some resources inside in the most cases.

* `cleanupFinalizers` - cleanup kopf finalizers from all namespaces during operator shutdown ([motivation](https://github.com/rgeraskin/remove-empty-ns-operator/issues/5#issuecomment-2710027536))

  If the finalizers cleanup takes longer than that in total (e.g. due to retries), the activity will not be finished in full, as the pod will be SIGKILL’ed by Kubernetes.

  So adjust the value of `terminationGracePeriodSeconds` if you have a lot of namespaces to cleanup.

## Development

1. Prepare local dev env with [mise](https://mise.jdx.dev): `mise install`
1. Install [pre-commit](https://pre-commit.com): `pre-commit install`
1. Use `mise tasks` for common tasks
1. Use [tilt](https://tilt.dev) for a development process, e.g. `tilt up`
1. Tests: `mise run test`

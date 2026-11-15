# Notes lab

Small web app and a Postgres database, wired the same way an EKS app is wired: GitHub Actions builds the image, a person updates the tag, Kustomize renders the Helm chart, Argo CD syncs the cluster.

KillerCoda can show the cluster half. The session lasts about an hour and then disappears. GitHub and Docker Hub keep the image and the desired state.

## What maps to the EKS setup

| EKS today | This lab |
| --- | --- |
| AWS EKS | KillerCoda Kubernetes playground |
| GitHub Actions | `.github/workflows/build-image.yml` |
| Docker Hub | `images.newName` / `images.newTag` |
| Helm chart | `deploy/charts/notes` |
| Kustomize overlay | `deploy/overlays/lab` |
| Argo CD | `deploy/argocd/application.yaml`, applied with kubectl |
| Someone edits the tag | `images.newTag` in the overlay |

GitHub Actions never talks to the cluster. It only pushes `docker.io/<user>/notes-web:<git sha>`.

## Layout

```text
app/                         Flask app and Dockerfile
deploy/charts/notes/         Helm chart: web, database, service, disruption budget
deploy/overlays/lab/         Kustomize: tag, 3 web replicas, NodePort, deploy order
deploy/argocd/application.yaml
```

The database is one replica on purpose. Its data lives on `emptyDir`, so a new pod starts empty. Three independent Postgres pods would be three different databases.

## One-hour path

Do the laptop steps before you start the KillerCoda timer.

1. The public GitHub repo is https://github.com/reddyvedanth/devops-gitops-lab. Create a public Docker Hub repo named `notes-web`.
2. In GitHub, add Actions secrets `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN`. The username is lowercase. The token is a Docker Hub personal access token with write access.
3. In `deploy/overlays/lab/kustomization.yaml`, set `images.newName` to `docker.io/<dockerhub-user>/notes-web`.
4. Commit and push `main`. Wait until the Actions run is green and copy the git SHA it prints.
5. Set `images.newTag` to that SHA, commit, and push. This second push does not rebuild the image. Only `app/**` changes trigger a build.
6. Open the [Kubernetes playground](https://killercoda.com/playgrounds/scenario/kubernetes). In its terminal:

```bash
git clone https://github.com/reddyvedanth/devops-gitops-lab.git
cd devops-gitops-lab
bash scripts/killercoda-up.sh
```

7. Watch the sync. Argo CD refreshes on its own every few minutes. To force it:

```bash
kubectl annotate application notes -n argocd argocd.argoproj.io/refresh=hard --overwrite
kubectl get application notes -n argocd
kubectl get deploy,pods,svc -n notes
```

8. Hit the app from the playground terminal:

```bash
curl -s localhost:30080/health
curl -s -X POST localhost:30080/notes \
  -H 'Content-Type: application/json' \
  -d '{"body":"hello from cli"}'
curl -s localhost:30080/notes
```

NodePort `30080` is only for the playground. The chart default is `ClusterIP`, which is what you would keep behind an ingress on EKS. The bootstrap script also sets Argo CD's Kustomize options to `--enable-helm --load-restrictor LoadRestrictionsNone`, because the chart sits next to the overlay instead of inside it.

## The loop you wanted to see

1. Change a string in `app/app.py`.
2. Push `main`. Actions builds and pushes a new SHA tag.
3. Put that SHA in `images.newTag`.
4. Push again.
5. Refresh the Argo CD application. `notes-web` rolls. `notes-db` stays.

```bash
kubectl get deploy notes-web -n notes \
  -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

The page footer shows the pod name and the version baked into that image.

## Deploy order

Order is declared on the resources in `deploy/overlays/lab/kustomization.yaml`:

| Wave | What comes up | Healthy means |
| --- | --- | --- |
| -1 | `notes` namespace | namespace exists |
| 0 | `notes-db-auth` Secret | secret exists |
| 1 | `notes-db` Service and Deployment | Postgres answers `pg_isready` |
| 2 | `notes-web` Service, Deployment, PodDisruptionBudget | `/ready` can query Postgres |

Kustomize list order does not wait. The `argocd.argoproj.io/sync-wave` annotations are what Argo CD waits on.

## Stateless database

```bash
curl -s -X POST localhost:30080/notes \
  -H 'Content-Type: application/json' \
  -d '{"body":"this will disappear"}'
kubectl delete pod -n notes -l app.kubernetes.io/component=db
kubectl rollout status deploy/notes-db -n notes
curl -s localhost:30080/notes
```

The second list is empty. There is no PersistentVolume.

## This folder and git

The lab directory needs its own git repository. The home directory above it is a separate repo. Commit and push from `devops-gitops-lab` only.

There is no Argo CD UI in this path. `kubectl get application` is the whole control plane you need.

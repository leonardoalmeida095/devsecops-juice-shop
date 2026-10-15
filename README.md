# POC SAST e DAST

Esta prova de conceito exercita um pipeline de segurança em cima de duas aplicações pequenas: um frontend e uma API. O código em si é um eco do navegador. O que a POC valida é o caminho do **Semgrep** (SAST) no GitHub Actions e do **ZAP** (DAST) como job no Cloud Run, com deploy privado e rollback quando o DAST reprova.

## Objetivo

Mostrar um fluxo contínuo em que:

1. o GitHub Actions autentica no GCP por Workload Identity Federation;
2. o **Semgrep** analisa o código-fonte (SAST) e interrompe o pipeline se houver achados de severidade alta/crítica (`ERROR`);
3. o frontend e a API sobem como serviços no Cloud Run;
4. o ZAP roda como job, varre a URL pública do load balancer e grava o relatório no Cloud Storage;
5. alerta de risco alto reprova a versão e o tráfego volta para a revisão anterior.

O frontend e a API existem para o ZAP ter o que percorrer: uma página, um formulário e uma chamada interna entre os dois serviços.

## Aplicação

O visitante abre o frontend. O serviço lê `User-Agent`, `Accept-Language` e `Accept` do pedido HTTP e envia esses campos, junto com uma nota opcional, para `POST /v1/client-info` na API. A página mostra os dois lados: o que o frontend encaminhou e o que a API enxergou na chamada interna.

| Serviço | Cloud Run | Ingress |
| --- | --- | --- |
| Frontend | `run-svc-frontend` | `internal-and-cloud-load-balancing`. A URL `*.run.app` não abre na internet. O load balancer alcança o serviço sem checagem de IAM. |
| API | `run-svc-backend` | Ingress `all`, com checagem de IAM. Só a `sa-sec-app` invoca. O ingress `internal` responde 404 para essa chamada: ela sai do frontend pela internet e o Cloud Run não a trata como tráfego interno. |

O frontend usa a conta `sa-sec-app` e não usa o conector VPC: assim a chamada para a API não é barrada pelo ingress. A API usa o conector `vpcconnector` do projeto host `vpc-host-0123` e fica com uma instância.

## SAST com Semgrep

A análise estática de segurança é realizada através do **Semgrep**, cobrindo o código Python (FastAPI/Uvicorn), Jinja2, Dockerfiles e scripts de automação.

### Regras Utilizadas
- **`auto`**: Regras inteligentes selecionadas automaticamente pelo registro do Semgrep baseadas nas linguagens e frameworks do projeto.
- **`p/owasp-top-ten`**: Foco nos 10 riscos mais críticos de segurança para aplicações web (ex: Injeção, Broken Access Control, Security Misconfiguration).
- **`p/cwe-top-25`**: Cobre as fraquezas mais perigosas do catálogo CWE.
- **`.semgrep.yml`**: Regras locais customizadas para detecção preventiva de:
  - Execução dinâmica perigosa (`eval` / `exec`).
  - Injeção de comandos de sistema operacional via `subprocess(..., shell=True)`.
  - Credenciais, chaves de API e tokens hardcoded no código.
  - XSS em templates desativando o autoescape do Jinja2.
  - SQL Injection via interpolação de strings.

### Execução Local

#### Opção 1: Via Docker (Sem necessidade de instalar Python/Semgrep local)
```bash
docker run --rm -v "${PWD}:/src" returntocorp/semgrep semgrep scan --config auto --config .semgrep.yml
```

#### Opção 2: Via CLI local (Python)
```bash
pip install semgrep
semgrep scan --config auto --config p/owasp-top-ten --config p/cwe-top-25 --config .semgrep.yml
```

Para validar se o pipeline bloquearia com código de saída não-zero em erros:
```bash
semgrep scan --config auto --config .semgrep.yml --error
```

## Pipeline CI/CD

Arquivo: `.github/workflows/pipeline.yaml`. Dispara no push da `main` ou manualmente.

1. Autenticação com a service account de CI via Workload Identity Federation.
2. **SAST com Semgrep**:
   - Varredura com regras gerenciadas e locais (`.semgrep.yml`).
   - Geração de relatório `semgrep-report.json` e `semgrep-report.sarif`.
   - Upload do artefato de execução e integração com a aba **Security > Code Scanning** do GitHub.
   - *Quality Gate*: Se houver qualquer vulnerabilidade com severidade `ERROR`, o pipeline é interrompido antes do build e deploy no GCP.
3. Build das imagens `frontend`, `backend` e `zap` no Artifact Registry, deploy dos dois serviços e publicação do job.
4. Espera `TARGET_URL/health/ready` responder 200. Esse endereço é o load balancer, não a URL direta do Cloud Run.
5. Executa o job `zap-security-scan` (DAST). Alerta **FAIL** (alto) reprova. Aviso médio fica no relatório.
6. Se reprovar, devolve 100% do tráfego para a revisão anterior de cada serviço.
7. O relatório vai para `gs://gcs_zap/dast/<run>/` e para o artifact `zap-report`.

## O que você associa no load balancer

O pipeline não cria NEG, backend service nem regra no balanceador. Depois do primeiro deploy do frontend:

1. Crie um NEG serverless regional em `us-central1` apontando para `run-svc-frontend`.
2. Crie o backend service e anexe esse NEG.
3. Aponte o URL map do `lb-external-uscentral` (projeto `vpc-host-0123`) para esse backend.
4. O DNS de `TARGET_URL` precisa cair nesse balanceador. O valor configurado é `http://sec-app-lab.souzatech.cloud`.

Enquanto o NEG não estiver no load balancer, o job de DAST espera o health check e, se não responder, reprova e faz rollback.

## Variáveis do repositório

| Variável | Uso |
| --- | --- |
| `PROJECT_ID` | Projeto de serviço, `sec-lab-510100`. |
| `REGION` | `us-central1`. |
| `WIF_SA` | Service account de CI. |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Provider do Workload Identity. |
| `APP_SA` | Service account de execução dos dois serviços. |
| `ARTIFACT_REPO` | Repositório Docker, `repo-sec-web-app`. |
| `TARGET_URL` | URL que o ZAP varre. |

A conta de CI precisa de `roles/iam.serviceAccountUser` em `APP_SA` e em `zap-job`, e de escrita no Artifact Registry.

## Local

```powershell
docker compose up --build
```

O frontend fica em [http://127.0.0.1:8080](http://127.0.0.1:8080) e a API em [http://127.0.0.1:8081](http://127.0.0.1:8081). No compose a chamada interna não usa identity token.

#!/bin/sh
# HTTPS pelo IP da máquina, sem domínio (profile `ip`).
#
# 1. Descobre o IP público (ou usa KURO_PUBLIC_IP, se o .env definir).
# 2. Sobe o Caddy com a CA interna dele: certificado emitido para o IP, renovado
#    sozinho. Sem Let's Encrypt, então sem porta 80/443, sem DNS e sem cota.
# 3. Publica no volume `kuro_public` o que o `kuro mcp-config` precisa para montar
#    a conexão: a URL e o certificado da CA raiz. Só o público: a chave privada da
#    CA fica no volume do Caddy, que o agent-service não monta.
set -eu

PORT="${KURO_IP_PORT:-58443}"
PUBLIC_DIR=/kuro-public

# Este profile põe o serviço na internet. Sem chave de API, conversas, prompts e
# credenciais ficariam abertos a quem achasse o IP: só sobe com a autenticação ligada.
if [ "${KURO_IP_ALLOW_OPEN:-}" != "1" ]; then
	health="$(wget -qO- -T 10 http://agent-service:8000/health 2>/dev/null || true)"
	case "$health" in
		*'"auth":"enabled"'* | *'"auth": "enabled"'*) ;;
		*)
			echo "kuro: recusei publicar o serviço pelo IP: a autenticação está desligada (ou o agent-service não respondeu)." >&2
			echo "kuro: defina ADMIN_API_KEY e RUNTIME_API_KEY no .env (openssl rand -hex 32) e rode docker compose up -d de novo." >&2
			echo "kuro: só para teste local, KURO_IP_ALLOW_OPEN=1 pula esta verificação." >&2
			sleep 30 # sem isso o restart do Docker repete a mensagem sem parar
			exit 1
			;;
	esac
fi

if [ -z "${KURO_PUBLIC_IP:-}" ]; then
	for url in https://api.ipify.org https://ifconfig.me/ip https://icanhazip.com; do
		KURO_PUBLIC_IP="$(wget -qO- -T 5 "$url" 2>/dev/null | tr -d ' \r\n' || true)"
		case "$KURO_PUBLIC_IP" in
			*[!0-9a-fA-F.:]* | "") KURO_PUBLIC_IP="" ;;
			*) break ;;
		esac
	done
fi
if [ -z "$KURO_PUBLIC_IP" ]; then
	echo "kuro: não consegui descobrir o IP público desta máquina. Defina KURO_PUBLIC_IP no .env." >&2
	exit 1
fi

# IPv6 vai entre colchetes na URL e no endereço do site.
case "$KURO_PUBLIC_IP" in
	*:*) KURO_SITE_HOST="[$KURO_PUBLIC_IP]" ;;
	*) KURO_SITE_HOST="$KURO_PUBLIC_IP" ;;
esac
export KURO_PUBLIC_IP KURO_SITE_HOST KURO_IP_PORT="$PORT"
URL="https://$KURO_SITE_HOST:$PORT"
echo "kuro: HTTPS por IP em $URL (CA própria do Caddy)"

caddy run --config /etc/caddy/Caddyfile --adapter caddyfile &
pid=$!
trap 'kill -TERM "$pid" 2>/dev/null' TERM INT

# A CA raiz nasce no primeiro start e fica no volume do Caddy (até 2036). Espera
# por ela e a publica junto com a URL.
root=/data/caddy/pki/authorities/local/root.crt
i=0
while [ ! -s "$root" ] && [ "$i" -lt 60 ]; do
	sleep 1
	i=$((i + 1))
done
if [ -s "$root" ]; then
	mkdir -p "$PUBLIC_DIR"
	cp "$root" "$PUBLIC_DIR/ca.crt"
	# É um certificado público: legível por qualquer usuário do agent-service.
	chmod 644 "$PUBLIC_DIR/ca.crt"
	printf '%s\n' "$URL" > "$PUBLIC_DIR/url"
else
	echo "kuro: a CA do Caddy não apareceu em 60 s; o kuro mcp-config não vai achar o certificado." >&2
fi

wait "$pid"

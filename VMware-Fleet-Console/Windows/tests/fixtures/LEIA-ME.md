# Ficheiros de teste · Test fixtures

`servidor-teste.crt` e `servidor-teste.key` são um certificado auto-assinado
**só para testes**, emitido para `vfc-teste.invalid` (um nome que, por definição,
não existe). Servem um único propósito: o servidor HTTPS de bolso que corre em
`127.0.0.1` durante o `test_export.py`, para a exportação ser testada contra um
certificado fixado a sério — exactamente como um ESXi de fábrica.

Não protegem nada nem dão acesso a nada. Não os use fora dos testes.

*A self-signed certificate **for tests only**, issued to `vfc-teste.invalid`,
used by the local HTTPS server in `test_export.py`. It protects nothing and
grants access to nothing.*

<sub>Created by Redfox using Claude</sub>

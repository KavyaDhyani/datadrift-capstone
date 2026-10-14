{{- define "datadrift.fullname" -}}
{{- .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end }}

{{- define "datadrift.labels" -}}
app.kubernetes.io/part-of: datadrift
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}

{{/* Selector labels for one component: include "datadrift.selector" (list . "backend") */}}
{{- define "datadrift.selector" -}}
app.kubernetes.io/instance: {{ (index . 0).Release.Name }}
app.kubernetes.io/component: {{ index . 1 }}
{{- end }}

{{- define "datadrift.image" -}}
{{- $tag := required (printf "%s.image.tag is required (use the Git commit SHA)" .name) .image.tag -}}
{{ .image.repository }}:{{ $tag }}
{{- end }}

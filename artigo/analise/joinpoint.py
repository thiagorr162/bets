"""2. Regressão segmentada (joinpoint) binomial negativa com offset, escolha das quebras, bootstrap e medidas de efeito."""

from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from itertools import combinations, pairwise, product
from multiprocessing import get_context

import numpy as np
import statsmodels.api as sm
from comum import (
    BLOCO,
    FIM_APS,
    FIM_CAPS,
    INICIO,
    INICIO_APS,
    KMAX,
    MIN_SEG,
    NUM,
    PANDEMIA,
    dec,
    fmt_mes,
    fmt_p,
    num,
    out,
    pct,
    r0,
)
from scipy import optimize, special

# %% 2. Regressão segmentada (joinpoint) -----------------------------------------------------------------------------
#   g(E[y_t]) = offset_t + const + 11 dummies de mês + pandemia + β·t + Σ_k δ_k (t − τ_k)+
# NB2 com link log (offset = log do denominador) ou binomial com link logit (y de n). Segmentos contínuos.

def mes_mais(m0: str, k) -> str:
    a, m = divmod(int(m0[:4]) * 12 + int(m0[4:]) - 1 + int(k), 12)
    return f"{a}{m + 1:02d}"


def tempo(meses):
    m0 = int(meses[0][:4]) * 12 + int(meses[0][4:])
    return np.array([int(m[:4]) * 12 + int(m[4:]) - m0 for m in meses], float)


def base(meses, pandemia=True):
    """Intercepto, dummies de mês, indicador de pandemia (se houver meses de pandemia na série) e t (último)."""
    mes, t = np.array([int(m[4:]) for m in meses]), tempo(meses)
    cols, nomes = [np.ones(len(meses))] + [(mes == k) * 1.0 for k in range(2, 13)], ["const"] + [f"mes{k}" for k in range(2, 13)]
    if pandemia:
        cols.append(np.array([PANDEMIA[0] <= m <= PANDEMIA[1] for m in meses], float))
        nomes.append("pandemia")
    return np.column_stack(cols + [t]), nomes + ["t"], t


def base_z(meses, pandemia=True, z=None):
    """`base` com covariáveis extras z (n × p) inseridas antes de t (t continua sendo a coluna antes das quebras)."""
    X0, nomes, t = base(meses, pandemia)
    if z is None:
        return X0, nomes, t
    z = np.asarray(z, float).reshape(len(meses), -1)
    return (np.column_stack([X0[:, :-1], z, X0[:, -1]]),
            nomes[:-1] + [f"z{j + 1}" for j in range(z.shape[1])] + ["t"], t)


def hinges(t, taus):
    return np.column_stack([np.maximum(t - tau, 0.0) for tau in taus]) if len(taus) else np.empty((len(t), 0))


# IRLS mínimo (só para a busca das quebras e o bootstrap, que exigem milhares de ajustes; o ajuste reportado
# é o do statsmodels, em `ajustar`)
def _medias(X, beta, off, fam, n, alpha):
    eta = np.clip(off + X @ beta, -50, 50)
    if fam == "nb":
        mu = np.exp(eta)
        return eta, mu, mu / (1 + alpha * mu)
    p = np.clip(special.expit(eta), 1e-12, 1 - 1e-12)
    return eta, n * p, np.maximum(n * p * (1 - p), 1e-10)


def _desvio(y, mu, fam, n=None, alpha=0.0):
    with np.errstate(divide="ignore", invalid="ignore"):
        t1 = np.where(y > 0, y * np.log(y / mu), 0.0)
        if fam == "nb":
            return 2 * np.sum(t1 - (y + 1 / alpha) * np.log((1 + alpha * y) / (1 + alpha * mu)))
        return 2 * np.sum(t1 + np.where(n - y > 0, (n - y) * np.log((n - y) / (n - mu)), 0.0))


def _irls(X, y, off, fam, n=None, alpha=0.0, it=100, tol=1e-8):
    p0 = np.log(np.maximum(y, 0.5)) if fam == "nb" else special.logit((y + 0.5) / (n + 1.0))
    beta = np.linalg.lstsq(X, p0 - off, rcond=None)[0]
    eta, mu, w = _medias(X, beta, off, fam, n, alpha)
    dev = _desvio(y, mu, fam, n, alpha)
    for _ in range(it):
        z = eta - off + (y - mu) / (mu if fam == "nb" else w)
        new = np.linalg.lstsq(X * np.sqrt(w)[:, None], z * np.sqrt(w), rcond=None)[0]
        for _ in range(30):  # reduz o passo se o desvio piorar
            eta_n, mu_n, w_n = _medias(X, new, off, fam, n, alpha)
            dev_n = _desvio(y, mu_n, fam, n, alpha)
            if np.isfinite(dev_n) and dev_n <= dev + 1e-10:
                break
            new = (new + beta) / 2
        conv = abs(dev - dev_n) < tol * (abs(dev_n) + 0.1)
        beta, eta, mu, w, dev = new, eta_n, mu_n, w_n, dev_n
        if conv:
            break
    return beta, mu


def _loglik_nb(y, mu, alpha):
    r = 1 / alpha
    return np.sum(special.gammaln(y + r) - special.gammaln(r) - special.gammaln(y + 1)
                  + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu)))


def buscar(y, X0, t, k, fam, off, n, alpha):
    """Posições das k quebras que minimizam o desvio (busca exaustiva; ≥ MIN_SEG meses entre quebras e pontas)."""
    if k == 0:
        return ()
    nt = int(t.max()) + 1

    def ok(c):
        return c[0] >= MIN_SEG and c[-1] <= nt - MIN_SEG and all(b - a >= MIN_SEG for a, b in pairwise(c))

    def desvio(c):
        return _desvio(y, _irls(np.column_stack([X0, hinges(t, c)]), y, off, fam, n, alpha)[1], fam, n, alpha)

    passo = 1 if k <= 2 else 3  # k = 3: grade a cada 3 meses e refinamento local
    melhor = min((c for c in combinations(range(MIN_SEG, nt - MIN_SEG + 1, passo), k) if ok(c)), key=desvio)
    if passo > 1:
        melhor = min((c for c in product(*[range(b - 2, b + 3) for b in melhor]) if ok(c)), key=desvio)
    return tuple(melhor)


@dataclass
class Ajuste:
    fam: str
    meses: list
    taus: tuple
    beta: np.ndarray
    nomes: list
    mu: np.ndarray
    alpha: float
    phi: float
    desvio: float
    crit: float  # BIC (NB) ou QBIC (binomial, preenchido em `selecionar`)
    y: np.ndarray
    n: np.ndarray | None
    off: np.ndarray
    X: np.ndarray
    pandemia: bool
    boot: dict = field(default_factory=dict)

    @property
    def k(self):
        return len(self.taus)

    def contraste(self, s):
        """Vetor c tal que c·β = inclinação mensal do segmento s (β_t + Σ_{j<s} δ_j)."""
        c, it = np.zeros(len(self.beta)), self.nomes.index("t")
        c[it:it + s + 1] = 1
        return c

    def segmentos(self):
        m0 = self.meses[0]
        q = [mes_mais(m0, tau) for tau in self.taus]
        return list(zip([m0] + q, q + [self.meses[-1]]))


def ajustar(y, meses, taus, fam, off=None, n=None, pandemia=True, z=None) -> Ajuste:
    off = np.zeros(len(y)) if off is None else off
    X0, nomes, t = base_z(meses, pandemia, z)
    X = np.column_stack([X0, hinges(t, taus)])
    nomes = nomes + [f"delta{j + 1}" for j in range(len(taus))]
    if fam == "nb":
        # como o glm.nb do R: alpha por máxima verossimilhança perfilada, β por GLM com alpha fixo
        alpha = float(np.exp(optimize.minimize_scalar(
            lambda la: -_loglik_nb(y, _irls(X, y, off, "nb", alpha=np.exp(la))[1], np.exp(la)),
            bounds=(np.log(1e-6), np.log(10)), method="bounded", options={"xatol": 1e-5}).x))
        r = sm.GLM(y, X, family=sm.families.NegativeBinomial(alpha=alpha), offset=off).fit()
        if not r.converged:
            print(f"  ! binomial negativa não convergiu (quebras {taus})")
        beta, mu = r.params, r.mu
        dev = _desvio(y, mu, "nb", alpha=alpha)
        crit, phi = -2 * _loglik_nb(y, mu, alpha) + (X.shape[1] + 1 + len(taus)) * np.log(len(y)), 1.0  # + alpha + posições
    else:
        r = sm.GLM(np.column_stack([y, n - y]), X, family=sm.families.Binomial()).fit()
        beta, mu, alpha = r.params, n * r.mu, 0.0
        dev = r.deviance
        phi = float(np.sum((y - mu) ** 2 / (mu * (1 - mu / n))) / (len(y) - X.shape[1]))
        crit = np.nan
    return Ajuste(fam, meses, tuple(taus), beta, nomes, mu, alpha, phi, dev, crit, y, n, off, X, pandemia)


def selecionar(y, meses, fam, off=None, n=None, kmax=KMAX, k_fixo=None, pandemia=True, z=None):
    """Ajusta K = 0..kmax quebras e escolhe o menor K com critério a menos de 2 pontos do mínimo."""
    y = np.asarray(y, float)
    off = np.zeros(len(y)) if off is None else off
    X0, _, t = base_z(meses, pandemia, z)
    alpha0 = None
    if fam == "nb":  # alpha de trabalho na busca: modelo flexível (quebras a cada 12 meses)
        alpha0 = ajustar(y, meses, tuple(range(MIN_SEG, int(t.max()) - MIN_SEG + 1, 12)), fam, off, pandemia=pandemia,
                         z=z).alpha
    todos = {}
    for k in (range(kmax + 1) if k_fixo is None else [k_fixo]):
        taus = buscar(y, X0, t, k, fam, off, n, alpha0)
        a = ajustar(y, meses, taus, fam, off, n, pandemia, z)
        if fam == "nb" and k:  # refaz a busca com o alpha do próprio modelo
            taus2 = buscar(y, X0, t, k, fam, off, n, a.alpha)
            a = a if taus2 == taus else ajustar(y, meses, taus2, fam, off, n, pandemia, z)
        todos[k] = a
    if fam == "bin":  # QBIC com phi do modelo mais flexível
        phi = max(todos[max(todos)].phi, 1.0)
        for k, a in todos.items():
            a.crit = a.desvio / phi + (a.X.shape[1] + k) * np.log(len(y))
    cmin = min(a.crit for a in todos.values())
    return min((a for a in todos.values() if a.crit <= cmin + 2), key=lambda a: a.k), todos


def sorteio_blocos(B: int, seed=1):
    """Um único sorteio de blocos de 6 meses de calendário, usado por todas as séries: a réplica b da APS e a do
    CAPS reamostram os mesmos meses (bootstrap conjunto; preserva choques comuns às duas redes).
    Linha b: para cada mês de calendário desde jan/2018, o mês cujo resíduo entra no lugar dele."""
    total = int(tempo([INICIO, FIM_APS])[1]) + 1
    lo = int(tempo([INICIO, INICIO_APS])[1])  # só blocos que existem nas duas séries
    hi = int(tempo([INICIO, FIM_CAPS])[1]) - BLOCO + 1
    ini = np.random.default_rng(seed).integers(lo, hi + 1, (B, int(np.ceil(total / BLOCO))))
    return (ini[:, :, None] + np.arange(BLOCO)).reshape(B, -1)[:, :total]


def bootstrap(aj: Ajuste, mapa: np.ndarray, processos: int):
    """Bootstrap por blocos móveis dos resíduos de Pearson (K fixo); refaz a busca das quebras em cada réplica."""
    partes = [(aj, mapa[p]) for p in np.array_split(np.arange(len(mapa)), processos) if len(p)]
    with ProcessPoolExecutor(len(partes), mp_context=get_context("fork")) as ex:
        res = list(ex.map(_boot, partes))
    aj.boot = {"taus": np.vstack([r[0] for r in res]), "incl": np.vstack([r[1] for r in res]),
              "beta": np.vstack([r[2] for r in res])}


def _boot(args):
    aj, mapa = args
    B = len(mapa)
    sd = np.sqrt(aj.mu + aj.alpha * aj.mu ** 2) if aj.fam == "nb" else np.sqrt(aj.mu * (1 - aj.mu / aj.n))
    r = (aj.y - aj.mu) / sd
    r -= r.mean()
    X0, _, t = base(aj.meses, aj.pandemia)
    c0 = int(tempo([INICIO, aj.meses[0]])[1])
    cal = c0 + t.astype(int)  # mês de calendário de cada observação
    taus_b, incl_b, beta_b = [], [], []
    for linha in mapa:
        ys = np.clip(np.round(aj.mu + sd * r[linha[cal] - c0]), 0, None if aj.fam == "nb" else aj.n)
        taus = buscar(ys, X0, t, aj.k, aj.fam, aj.off, aj.n, aj.alpha)
        beta, _ = _irls(np.column_stack([X0, hinges(t, taus)]), ys, aj.off, aj.fam, aj.n, aj.alpha)
        taus_b.append(taus)
        incl_b.append([aj.contraste(s) @ beta for s in range(aj.k + 1)])
        beta_b.append(beta)
    return np.array(taus_b, float).reshape(B, aj.k), np.array(incl_b).reshape(B, aj.k + 1), np.array(beta_b)


# Resumos
def vpa(inclinacao_mensal):
    """Variação percentual anual: 100·(exp(12·inclinação) − 1)."""
    return 100 * (np.exp(12 * np.asarray(inclinacao_mensal)) - 1)


def vpam(aj: Ajuste, ini=None, fim=None):
    """VPA média (AAPC) entre dois meses: média das inclinações mensais, ponderada pelos meses de cada segmento.
    Retorna (estimativa, limite inferior, limite superior); os limites vêm do bootstrap (nan sem bootstrap)."""
    t = tempo([aj.meses[0], ini or aj.meses[0], fim or aj.meses[-1]])
    i = np.arange(t[1], t[2])
    c = np.mean([aj.contraste(int(np.sum(np.array(aj.taus) <= j))) for j in i], axis=0)
    if not aj.boot:
        return vpa(c @ aj.beta), np.nan, np.nan
    b = [np.mean(inc[np.searchsorted(np.asarray(tb), i + 0.5)]) for tb, inc in zip(aj.boot["taus"], aj.boot["incl"])]
    return (vpa(c @ aj.beta), *vpa(np.percentile(b, [2.5, 97.5])))


def ljung_box(aj: Ajuste, lags=12):
    from statsmodels.stats.diagnostic import acorr_ljungbox
    sd = np.sqrt(aj.mu + aj.alpha * aj.mu ** 2) if aj.fam == "nb" else np.sqrt(aj.mu * (1 - aj.mu / aj.n))
    return float(acorr_ljungbox((aj.y - aj.mu) / sd, lags=[lags])["lb_pvalue"].iloc[0])


def ic_quebra(aj: Ajuste, j=-1):
    q = np.percentile(aj.boot["taus"][:, j], [2.5, 97.5])
    return mes_mais(aj.meses[0], np.floor(q[0])), mes_mais(aj.meses[0], np.ceil(q[1]))


def preditor_base(aj: Ajuste, beta, taus, tipo="prolongada"):
    """Preditor linear (com offset e sazonalidade) da linha de base, que só difere do ajuste depois da quebra final.
    'prolongada': o segmento anterior à quebra final continua com a mesma inclinação (δ final = 0).
    'congelada': a taxa fica no nível que tinha na quebra final (inclinação zero depois dela)."""
    X0, _, t = base(aj.meses, aj.pandemia)
    taus = tuple(np.asarray(taus, float))
    if tipo == "congelada":
        t = np.minimum(t, taus[-1])
        X0 = X0.copy()
        X0[:, -1] = t
    X = np.column_stack([X0, hinges(t, taus[:-1]), np.zeros(len(t))])
    return aj.off + X @ beta


def excesso(aj: Ajuste, ini, fim, tipo="prolongada"):
    """Observado, esperado pela linha de base e excesso numa janela de calendário fixa [ini, fim], igual em todas as
    réplicas. IC95% bootstrap: em cada réplica a linha de base é refeita com o β e as quebras da réplica; o observado
    fica fixo, então o intervalo é a incerteza da linha de base (inclusive sobre onde fica a quebra)."""
    w = np.array([ini <= m <= fim for m in aj.meses])
    obs = float(aj.y[w].sum())
    esp = float(np.exp(preditor_base(aj, aj.beta, aj.taus, tipo)[w]).sum())
    esp_b = [np.exp(preditor_base(aj, b, tb, tipo)[w]).sum() for b, tb in zip(aj.boot["beta"], aj.boot["taus"])]
    lo, hi = np.percentile(esp_b, [2.5, 97.5])
    return {"obs": obs, "esp": esp, "esp_lo": lo, "esp_hi": hi, "exc": obs - esp, "exc_lo": obs - hi, "exc_hi": obs - lo}


def relatar(rotulo, aj: Ajuste, todos=None):
    """Bloco de texto de um modelo: seleção de K, segmentos (VPA), quebras e VPAM. IC95% por bootstrap."""
    disp = f"alpha = {dec(aj.alpha, 3)}" if aj.fam == "nb" else f"phi = {dec(aj.phi)}"
    out(f"\n{rotulo}\n  [{'binomial negativa' if aj.fam == 'nb' else 'binomial (logit)'}; {disp}; "
        f"Ljung-Box(12) dos resíduos p = {fmt_p(ljung_box(aj))}]")
    if todos:
        for k, a in todos.items():
            q = ", ".join(fmt_mes(mes_mais(a.meses[0], tau)) for tau in a.taus) or "—"
            out(f"  K = {k}: {'QBIC' if a.fam == 'bin' else 'BIC'} = {num(a.crit, 1):>9}   quebras: {q}"
                + ("   <- escolhido" if k == aj.k else ""))
    for s, (ini, fim) in enumerate(aj.segmentos()):
        linha = f"  segmento {s + 1}: {fmt_mes(ini)}–{fmt_mes(fim)}   VPA {pct(vpa(aj.contraste(s) @ aj.beta))}"
        if aj.boot:
            bl, bh = vpa(np.percentile(aj.boot["incl"][:, s], [2.5, 97.5]))
            linha += f" (IC95% {pct(bl)}; {pct(bh)})"
        out(linha)
    for j, tau in enumerate(aj.taus):
        linha = f"  quebra {j + 1}: {fmt_mes(mes_mais(aj.meses[0], tau))}"
        if aj.boot:
            a, b = ic_quebra(aj, j)
            linha += f" (IC95% {fmt_mes(a)}–{fmt_mes(b)})"
        out(linha)
    r = vpam(aj)
    out(f"  VPAM {fmt_mes(aj.meses[0])}–{fmt_mes(aj.meses[-1])}: {pct(r[0])}"
        + (f" (IC95% {pct(r[1])}; {pct(r[2])})" if aj.boot else ""))


def guardar(chave, aj: Ajuste):
    """Grava em NUM as quebras, as VPA de cada segmento (com IC95% bootstrap, '_bli'/'_bls') e a VPAM de um modelo.
    Atalhos: '.ult*' = último segmento; '.qult*' = quebra que abre o último segmento."""
    for j, tau in enumerate(aj.taus):
        NUM[f"{chave}.q{j + 1}"] = fmt_mes(mes_mais(aj.meses[0], tau))
        if aj.boot:
            lo, hi = ic_quebra(aj, j)
            NUM[f"{chave}.q{j + 1}_li"], NUM[f"{chave}.q{j + 1}_ls"] = fmt_mes(lo), fmt_mes(hi)
    for s, (ini, fim) in enumerate(aj.segmentos()):
        b = f"{chave}.s{s + 1}"
        NUM.update({b: r0(vpa(aj.contraste(s) @ aj.beta)), b + "_ini": fmt_mes(ini), b + "_fim": fmt_mes(fim)})
        if aj.boot:
            bl, bh = vpa(np.percentile(aj.boot["incl"][:, s], [2.5, 97.5]))
            NUM[b + "_bli"], NUM[b + "_bls"] = r0(bl), r0(bh)
    for suf in ("", "_bli", "_bls", "_ini", "_fim"):
        if f"{chave}.s{aj.k + 1}{suf}" in NUM:
            NUM[f"{chave}.ult{suf}"] = NUM[f"{chave}.s{aj.k + 1}{suf}"]
    for suf in ("", "_li", "_ls"):
        if aj.k and f"{chave}.q{aj.k}{suf}" in NUM:
            NUM[f"{chave}.qult{suf}"] = NUM[f"{chave}.q{aj.k}{suf}"]
    r = vpam(aj)
    NUM.update({f"{chave}.k": aj.k, f"{chave}.vpam": r0(r[0]), f"{chave}.lb": fmt_p(ljung_box(aj))})
    if aj.boot:
        NUM[f"{chave}.vpam_bli"], NUM[f"{chave}.vpam_bls"] = r0(r[1]), r0(r[2])
    if aj.fam == "nb":
        NUM[f"{chave}.alpha"] = dec(aj.alpha, 3)
    else:
        NUM[f"{chave}.phi"] = dec(aj.phi, 1)


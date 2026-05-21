# ENGINEERING_SPEC.md — SmartQuotation

> **Módulo:** `engineering/`
> **Status:** Aprovado | **Versão:** 1.0
> **Referência:** ARCHITECTURE.md ADR-005, DATA_MODEL.md §3.6

---

## 1. Princípios Inegociáveis

1. **Zero dependência de Django.** Nenhum import de `django.*` em nenhum arquivo de `engineering/`.
2. **Funções puras.** Input → output. Sem efeitos colaterais, sem estado global, sem I/O.
3. **Pydantic v2 em tudo.** Todos os inputs e outputs são dataclasses Pydantic. Nunca `dict` nu.
4. **Pint para unidades.** Toda grandeza física que pode vir em unidades mistas (mm/in, MPa/psi, kg/lb, °C/°F) usa `pint.Quantity`. A função converte internamente para SI antes de calcular.
5. **Decorator `@calculation` obrigatório.** Toda função de cálculo normativo usa o decorator. Sem exceção.
6. **Referência à norma em toda função.** Docstring inclui seção exata da norma aplicada.
7. **Nunca retornar resultado silenciosamente errado.** Input fora de range → `CalculationError` com mensagem estruturada. Nunca retornar zero ou None sem exceção.

---

## 2. Estrutura de Pastas

```
engineering/
├── __init__.py
├── units.py                    # pint unit registry customizado
├── versioning.py               # decorator @calculation
├── snapshot.py                 # serialização para CalculationSnapshot
├── exceptions.py               # CalculationError, ValidationError
├── asme/
│   ├── __init__.py
│   ├── common/
│   │   ├── __init__.py
│   │   ├── allowable_stress.py # lookup de S value por material + temperatura
│   │   └── joint_efficiency.py # E values ASME
│   └── viii_div1/
│       ├── __init__.py
│       ├── shell.py            # UG-27 — casco cilíndrico
│       ├── heads.py            # UG-32 + UG-34 — tampos
│       ├── nozzles.py          # UG-37 — reforço de bocais
│       └── weight.py           # cálculo de peso por componente
├── tema/
│   ├── __init__.py
│   ├── shell_side.py           # lado casco
│   ├── tube_side.py            # lado tubo
│   ├── tubesheets.py           # espelhos
│   ├── tube_bundle.py          # feixe tubular
│   └── baffles.py              # chicanas
└── pricing/                    # módulo de custo — separado mas mesmo padrão
    ├── __init__.py
    ├── material_cost.py
    ├── labor_cost.py
    └── price_formation.py
```

---

## 3. Unit Registry (`engineering/units.py`)

```python
import pint

ureg = pint.UnitRegistry()

# Aliases customizados para unidades comuns em caldeiraria brasileira
ureg.define("kgf_cm2 = 0.0980665 MPa")  # pressão em kgf/cm²
ureg.define("psi = 6894.757 Pa")

# Grandezas de trabalho — sempre em SI internamente
PRESSURE_SI = ureg.pascal
STRESS_SI = ureg.megapascal
LENGTH_SI = ureg.millimeter      # mm como padrão interno (não m — escala de caldeiraria)
TEMP_SI = ureg.degC
DENSITY_SI = ureg.kilogram / ureg.meter**3
FORCE_SI = ureg.newton


def to_mm(value: pint.Quantity) -> float:
    """Converte qualquer unidade de comprimento para mm (float)."""
    return value.to(ureg.millimeter).magnitude


def to_mpa(value: pint.Quantity) -> float:
    """Converte qualquer unidade de pressão/tensão para MPa (float)."""
    return value.to(ureg.megapascal).magnitude


def to_celsius(value: pint.Quantity) -> float:
    """Converte qualquer temperatura para °C (float)."""
    return value.to(ureg.degC).magnitude


def to_kg_m3(value: pint.Quantity) -> float:
    """Converte qualquer densidade para kg/m³ (float)."""
    return value.to(ureg.kilogram / ureg.meter**3).magnitude
```

---

## 4. Decorator `@calculation` (`engineering/versioning.py`)

### Interface do decorator

```python
from typing import Callable, TypeVar
from functools import wraps

F = TypeVar("F", bound=Callable)


def calculation(
    version: str,           # SemVer — ex: "1.0.0"
    standard: str,          # Referência completa — ex: "ASME BPVC Sec. VIII Div.1 UG-27 (2021)"
    description: str = "",  # Descrição legível opcional
) -> Callable[[F], F]:
    """
    Decorator que registra metadados normativos em uma função de cálculo.

    Uso:
        @calculation(version="1.0.0", standard="ASME BPVC Sec. VIII Div.1 UG-27 (2021)")
        def calc_shell_thickness(inputs: ShellInput) -> ShellOutput:
            ...

    O decorator:
    - Injeta atributos __calc_version__, __calc_standard__ na função
    - Envolve a função com validação Pydantic de inputs (já feita pelo Pydantic v2)
    - Propaga CalculationError sem alteração
    - Envolve exceções inesperadas em CalculationError com contexto
    """
    def decorator(func: F) -> F:
        func.__calc_version__ = version
        func.__calc_standard__ = standard
        func.__calc_description__ = description

        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except CalculationError:
                raise
            except Exception as e:
                raise CalculationError(
                    code="UNEXPECTED_ERROR",
                    message=f"Erro inesperado em {func.__qualname__}: {e}",
                    function=func.__qualname__,
                    version=version,
                    standard=standard,
                ) from e

        wrapper.__calc_version__ = version
        wrapper.__calc_standard__ = standard
        wrapper.__calc_description__ = description
        return wrapper  # type: ignore

    return decorator
```

### Como extrair metadados para o snapshot

```python
def get_calc_metadata(func: Callable) -> dict:
    return {
        "function_name": f"{func.__module__}.{func.__qualname__}",
        "function_version": getattr(func, "__calc_version__", "unknown"),
        "standard_reference": getattr(func, "__calc_standard__", "unknown"),
    }
```

---

## 5. Exceções (`engineering/exceptions.py`)

```python
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CalculationError(Exception):
    """
    Erro estruturado de cálculo normativo.
    Sempre inclui o código de erro, função e norma para rastreabilidade.
    """
    code: str                           # ex: "PRESSURE_OUT_OF_RANGE"
    message: str                        # mensagem legível em português
    function: str = ""                  # ex: "engineering.asme.viii_div1.shell.calc_shell_thickness"
    version: str = ""                   # versão da função
    standard: str = ""                  # norma aplicada
    field: str = ""                     # campo que causou o erro (se aplicável)
    value: Any = None                   # valor inválido (se aplicável)
    context: dict = field(default_factory=dict)  # contexto adicional

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "function": self.function,
            "version": self.version,
            "standard": self.standard,
            "field": self.field,
            "value": str(self.value) if self.value is not None else None,
            "context": self.context,
        }


# Códigos de erro padrão
class ErrorCode:
    PRESSURE_OUT_OF_RANGE = "PRESSURE_OUT_OF_RANGE"
    TEMPERATURE_OUT_OF_RANGE = "TEMPERATURE_OUT_OF_RANGE"
    MATERIAL_NO_ALLOWABLE_STRESS = "MATERIAL_NO_ALLOWABLE_STRESS"
    THICKNESS_BELOW_MINIMUM = "THICKNESS_BELOW_MINIMUM"
    JOINT_EFFICIENCY_INVALID = "JOINT_EFFICIENCY_INVALID"
    GEOMETRY_INVALID = "GEOMETRY_INVALID"
    DIVISION_BY_ZERO = "DIVISION_BY_ZERO"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"
```

---

## 6. Snapshot (`engineering/snapshot.py`)

```python
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable
from datetime import datetime, timezone


@dataclass
class CalculationSnapshotData:
    """
    Estrutura serializada para gravar em CalculationSnapshot (banco).
    Produzida por build_snapshot() após cada execução do motor.
    """
    function_name: str
    function_version: str
    standard_reference: str
    inputs: dict            # inputs serializados (Pydantic .model_dump())
    outputs: dict           # outputs serializados (Pydantic .model_dump())
    inputs_hash: str        # SHA-256(json.dumps(inputs, sort_keys=True))
    calculated_at: str      # ISO8601 UTC


def build_snapshot(
    func: Callable,
    inputs_model,   # instância Pydantic (BaseModel)
    outputs_model,  # instância Pydantic (BaseModel)
) -> CalculationSnapshotData:
    """
    Constrói o snapshot de um cálculo para persistência.

    Uso (na camada Django — NÃO dentro do engineering/):
        snapshot = build_snapshot(calc_shell_thickness, inputs, outputs)
        CalculationSnapshot.objects.create(
            component=component,
            **snapshot.__dict__,
        )
    """
    inputs_dict = inputs_model.model_dump(mode="json")
    outputs_dict = outputs_model.model_dump(mode="json")
    inputs_json = json.dumps(inputs_dict, sort_keys=True, ensure_ascii=False)
    inputs_hash = hashlib.sha256(inputs_json.encode()).hexdigest()

    return CalculationSnapshotData(
        function_name=f"{func.__module__}.{func.__qualname__}",
        function_version=getattr(func, "__calc_version__", "unknown"),
        standard_reference=getattr(func, "__calc_standard__", "unknown"),
        inputs=inputs_dict,
        outputs=outputs_dict,
        inputs_hash=inputs_hash,
        calculated_at=datetime.now(timezone.utc).isoformat(),
    )
```

---

## 7. ASME VIII Div.1 — Casco Cilíndrico (UG-27)

### Arquivo: `engineering/asme/viii_div1/shell.py`

```python
from pydantic import BaseModel, Field, model_validator
from engineering.versioning import calculation
from engineering.exceptions import CalculationError, ErrorCode
from engineering.units import to_mm, to_mpa
import pint


# ── Input ──────────────────────────────────────────────────────────────────

class ShellInput(BaseModel):
    """
    Inputs para cálculo de espessura de casco cilíndrico.
    Todos os valores devem ser fornecidos em unidades SI (mm, MPa, °C).
    Use as funções to_mm() / to_mpa() para converter antes de instanciar.
    """
    design_pressure_mpa: float = Field(gt=0, description="Pressão de design em MPa")
    inner_radius_mm: float = Field(gt=0, description="Raio interno em mm")
    allowable_stress_mpa: float = Field(gt=0, description="Tensão admissível S em MPa (ASME Sec. II Parte D)")
    joint_efficiency: float = Field(default=1.0, ge=0.6, le=1.0, description="Eficiência de junta E (ASME UW-12)")
    corrosion_allowance_mm: float = Field(default=3.0, ge=0.0, description="Sobremetal de corrosão em mm")

    @model_validator(mode="after")
    def validate_pressure_stress_ratio(self) -> "ShellInput":
        # UG-27: fórmula (1) válida para P < 0.385·S·E
        limit = 0.385 * self.allowable_stress_mpa * self.joint_efficiency
        if self.design_pressure_mpa >= limit:
            raise CalculationError(
                code=ErrorCode.PRESSURE_OUT_OF_RANGE,
                message=(
                    f"Pressão de design ({self.design_pressure_mpa:.3f} MPa) ≥ 0.385·S·E "
                    f"({limit:.3f} MPa). Use a fórmula UG-27(c)(2) ou ASME Div.2."
                ),
                field="design_pressure_mpa",
                value=self.design_pressure_mpa,
            )
        return self


# ── Output ─────────────────────────────────────────────────────────────────

class ShellOutput(BaseModel):
    required_thickness_mm: float = Field(description="Espessura mínima requerida pela norma (sem CA) em mm")
    required_thickness_with_ca_mm: float = Field(description="Espessura mínima com sobremetal em mm")
    mawp_mpa: float = Field(description="MAWP — Máxima Pressão de Trabalho Admissível em MPa")
    formula_used: str = Field(description="Identificador da fórmula aplicada: 'UG-27c1' ou 'UG-27c2'")
    # Intermediários — gravados no snapshot para auditoria
    pr_term: float = Field(description="P·R (numerador da fórmula c1)")
    se_term: float = Field(description="S·E (denominador, fórmula c1)")
    se_06p_term: float = Field(description="S·E + 0.6·P (denominador, fórmula c2 — informativo)")


# ── Função principal ────────────────────────────────────────────────────────

@calculation(
    version="1.0.0",
    standard="ASME BPVC Section VIII Division 1 UG-27(c)(1) — 2021 Edition",
    description="Espessura mínima de casco cilíndrico sob pressão interna",
)
def calc_shell_thickness(inputs: ShellInput) -> ShellOutput:
    """
    Calcula a espessura mínima requerida de um casco cilíndrico sob pressão interna.

    Norma: ASME BPVC Sec. VIII Div.1 UG-27(c)
    Fórmula (1) — circunferential stress (governa para R/t > 2 ≈ t/R < 0.5):
        t = P·R / (S·E - 0.6·P)

    Fórmula (2) — longitudinal stress:
        t = P·R / (2·S·E + 0.4·P)

    A espessura requerida é o MAIOR resultado entre (1) e (2).
    MAWP é calculado revertendo a fórmula com a espessura adotada = t_required.
    """
    P = inputs.design_pressure_mpa
    R = inputs.inner_radius_mm
    S = inputs.allowable_stress_mpa
    E = inputs.joint_efficiency
    CA = inputs.corrosion_allowance_mm

    # Fórmula UG-27(c)(1) — tensão circunferencial (governa na maioria dos casos)
    denominator_c1 = S * E - 0.6 * P
    if denominator_c1 <= 0:
        raise CalculationError(
            code=ErrorCode.DIVISION_BY_ZERO,
            message=f"Denominador S·E - 0.6·P = {denominator_c1:.4f} ≤ 0. Verifique inputs.",
        )
    t_c1 = (P * R) / denominator_c1

    # Fórmula UG-27(c)(2) — tensão longitudinal
    t_c2 = (P * R) / (2 * S * E + 0.4 * P)

    # Espessura requerida = maior entre as duas fórmulas
    t_required = max(t_c1, t_c2)
    formula_used = "UG-27c1" if t_c1 >= t_c2 else "UG-27c2"

    # MAWP — revertendo fórmula c1 com t = t_required (sem CA)
    mawp = (S * E * t_required) / (R + 0.6 * t_required)

    return ShellOutput(
        required_thickness_mm=round(t_required, 4),
        required_thickness_with_ca_mm=round(t_required + CA, 4),
        mawp_mpa=round(mawp, 4),
        formula_used=formula_used,
        pr_term=round(P * R, 4),
        se_term=round(S * E, 4),
        se_06p_term=round(S * E - 0.6 * P, 4),
    )
```

---

## 8. ASME VIII Div.1 — Tampos (UG-32)

### Arquivo: `engineering/asme/viii_div1/heads.py`

```python
from enum import Enum
from pydantic import BaseModel, Field
from engineering.versioning import calculation
from engineering.exceptions import CalculationError, ErrorCode


class HeadType(str, Enum):
    TORIESPHERICAL = "toriespherical"   # UG-32(e) — Klöpper / ASME F&D
    ELLIPTICAL = "elliptical"           # UG-32(d) — 2:1
    HEMISPHERICAL = "hemispherical"     # UG-32(f)
    CONICAL = "conical"                 # UG-32(g) — sem knuckle
    FLAT = "flat"                       # UG-34


# ── Inputs por tipo ─────────────────────────────────────────────────────────

class TorisphericalHeadInput(BaseModel):
    design_pressure_mpa: float = Field(gt=0)
    inner_diameter_mm: float = Field(gt=0, description="Diâmetro interno do casco (D)")
    allowable_stress_mpa: float = Field(gt=0)
    joint_efficiency: float = Field(default=1.0, ge=0.6, le=1.0)
    corrosion_allowance_mm: float = Field(default=3.0, ge=0.0)
    # Para tampo toriesférico padrão ASME F&D: L = D, r = 0.06·D
    crown_radius_mm: float | None = Field(default=None, description="Raio de calota L. Se None: L = D")
    knuckle_radius_mm: float | None = Field(default=None, description="Raio de borda r. Se None: r = 0.06·D")


class EllipticalHeadInput(BaseModel):
    design_pressure_mpa: float = Field(gt=0)
    inner_diameter_mm: float = Field(gt=0)
    allowable_stress_mpa: float = Field(gt=0)
    joint_efficiency: float = Field(default=1.0, ge=0.6, le=1.0)
    corrosion_allowance_mm: float = Field(default=3.0, ge=0.0)
    aspect_ratio: float = Field(default=2.0, gt=1.0, description="D/(2h) — padrão 2:1 = 2.0")


class HemisphericalHeadInput(BaseModel):
    design_pressure_mpa: float = Field(gt=0)
    inner_radius_mm: float = Field(gt=0)
    allowable_stress_mpa: float = Field(gt=0)
    joint_efficiency: float = Field(default=1.0, ge=0.6, le=1.0)
    corrosion_allowance_mm: float = Field(default=3.0, ge=0.0)


class ConicalHeadInput(BaseModel):
    design_pressure_mpa: float = Field(gt=0)
    inner_diameter_mm: float = Field(gt=0, description="Diâmetro interno do casco D")
    half_apex_angle_deg: float = Field(gt=0, lt=30, description="Semiângulo α em graus (< 30°)")
    allowable_stress_mpa: float = Field(gt=0)
    joint_efficiency: float = Field(default=1.0, ge=0.6, le=1.0)
    corrosion_allowance_mm: float = Field(default=3.0, ge=0.0)


# ── Output (comum a todos os tipos) ─────────────────────────────────────────

class HeadOutput(BaseModel):
    head_type: HeadType
    required_thickness_mm: float
    required_thickness_with_ca_mm: float
    mawp_mpa: float
    factor_M_or_K: float | None = Field(default=None, description="Fator M (toriesférico) ou K (elíptico)")
    formula_reference: str


# ── Funções de cálculo ───────────────────────────────────────────────────────

@calculation(
    version="1.0.0",
    standard="ASME BPVC Section VIII Division 1 UG-32(e) — 2021 Edition",
    description="Espessura mínima de tampo toriesférico (F&D head)",
)
def calc_toriespherical_head(inputs: TorisphericalHeadInput) -> HeadOutput:
    """
    UG-32(e): t = 0.885·P·L / (S·E - 0.1·P)
    L = crown radius (raio de calota). Para tampo F&D padrão: L = D.
    """
    P = inputs.design_pressure_mpa
    D = inputs.inner_diameter_mm
    S = inputs.allowable_stress_mpa
    E = inputs.joint_efficiency
    CA = inputs.corrosion_allowance_mm
    L = inputs.crown_radius_mm if inputs.crown_radius_mm else D

    denominator = S * E - 0.1 * P
    if denominator <= 0:
        raise CalculationError(
            code=ErrorCode.DIVISION_BY_ZERO,
            message=f"S·E - 0.1·P = {denominator:.4f} ≤ 0",
        )
    t = (0.885 * P * L) / denominator
    mawp = (S * E * t) / (0.885 * L + 0.1 * t)

    return HeadOutput(
        head_type=HeadType.TORIESPHERICAL,
        required_thickness_mm=round(t, 4),
        required_thickness_with_ca_mm=round(t + CA, 4),
        mawp_mpa=round(mawp, 4),
        factor_M_or_K=None,
        formula_reference="UG-32(e): t = 0.885·P·L / (S·E - 0.1·P)",
    )


@calculation(
    version="1.0.0",
    standard="ASME BPVC Section VIII Division 1 UG-32(d) — 2021 Edition",
    description="Espessura mínima de tampo elíptico 2:1",
)
def calc_elliptical_head(inputs: EllipticalHeadInput) -> HeadOutput:
    """
    UG-32(d): t = P·D·K / (2·S·E - 0.2·P)
    K = (1/6)·[2 + (D/2h)²] = fator de forma elíptica.
    Para 2:1 (aspect_ratio=2.0): K = 1.0.
    """
    import math
    P = inputs.design_pressure_mpa
    D = inputs.inner_diameter_mm
    S = inputs.allowable_stress_mpa
    E = inputs.joint_efficiency
    CA = inputs.corrosion_allowance_mm
    AR = inputs.aspect_ratio  # D/(2h)

    K = (1 / 6) * (2 + AR ** 2)
    denominator = 2 * S * E - 0.2 * P
    if denominator <= 0:
        raise CalculationError(
            code=ErrorCode.DIVISION_BY_ZERO,
            message=f"2·S·E - 0.2·P = {denominator:.4f} ≤ 0",
        )
    t = (P * D * K) / denominator
    mawp = (2 * S * E * t) / (D * K + 0.2 * t)

    return HeadOutput(
        head_type=HeadType.ELLIPTICAL,
        required_thickness_mm=round(t, 4),
        required_thickness_with_ca_mm=round(t + CA, 4),
        mawp_mpa=round(mawp, 4),
        factor_M_or_K=round(K, 4),
        formula_reference="UG-32(d): t = P·D·K / (2·S·E - 0.2·P)",
    )


@calculation(
    version="1.0.0",
    standard="ASME BPVC Section VIII Division 1 UG-32(f) — 2021 Edition",
    description="Espessura mínima de tampo hemisférico",
)
def calc_hemispherical_head(inputs: HemisphericalHeadInput) -> HeadOutput:
    """
    UG-32(f): t = P·R / (2·S·E - 0.2·P)
    R = raio interno. Governado por tensão circunferencial.
    """
    P = inputs.design_pressure_mpa
    R = inputs.inner_radius_mm
    S = inputs.allowable_stress_mpa
    E = inputs.joint_efficiency
    CA = inputs.corrosion_allowance_mm

    denominator = 2 * S * E - 0.2 * P
    if denominator <= 0:
        raise CalculationError(
            code=ErrorCode.DIVISION_BY_ZERO,
            message=f"2·S·E - 0.2·P = {denominator:.4f} ≤ 0",
        )
    t = (P * R) / denominator
    mawp = (2 * S * E * t) / (R + 0.2 * t)

    return HeadOutput(
        head_type=HeadType.HEMISPHERICAL,
        required_thickness_mm=round(t, 4),
        required_thickness_with_ca_mm=round(t + CA, 4),
        mawp_mpa=round(mawp, 4),
        factor_M_or_K=None,
        formula_reference="UG-32(f): t = P·R / (2·S·E - 0.2·P)",
    )


@calculation(
    version="1.0.0",
    standard="ASME BPVC Section VIII Division 1 UG-32(g) — 2021 Edition",
    description="Espessura mínima de tampo cônico sem anel de reforço (α < 30°)",
)
def calc_conical_head(inputs: ConicalHeadInput) -> HeadOutput:
    """
    UG-32(g): t = P·D / (2·cos(α)·(S·E - 0.6·P))
    α = semiângulo do ápice. Válido apenas para α < 30°.
    """
    import math
    P = inputs.design_pressure_mpa
    D = inputs.inner_diameter_mm
    alpha_rad = math.radians(inputs.half_apex_angle_deg)
    S = inputs.allowable_stress_mpa
    E = inputs.joint_efficiency
    CA = inputs.corrosion_allowance_mm

    cos_alpha = math.cos(alpha_rad)
    denominator = 2 * cos_alpha * (S * E - 0.6 * P)
    if denominator <= 0:
        raise CalculationError(
            code=ErrorCode.DIVISION_BY_ZERO,
            message=f"2·cos(α)·(S·E - 0.6·P) = {denominator:.4f} ≤ 0",
        )
    t = (P * D) / denominator
    mawp = (2 * cos_alpha * S * E * t) / (D + 1.2 * cos_alpha * t)

    return HeadOutput(
        head_type=HeadType.CONICAL,
        required_thickness_mm=round(t, 4),
        required_thickness_with_ca_mm=round(t + CA, 4),
        mawp_mpa=round(mawp, 4),
        factor_M_or_K=round(cos_alpha, 6),
        formula_reference="UG-32(g): t = P·D / (2·cos(α)·(S·E - 0.6·P))",
    )
```

---

## 9. ASME VIII Div.1 — Peso de Componentes (`engineering/asme/viii_div1/weight.py`)

```python
import math
from pydantic import BaseModel, Field
from engineering.versioning import calculation


class ShellWeightInput(BaseModel):
    outer_diameter_mm: float = Field(gt=0)
    thickness_mm: float = Field(gt=0)
    length_mm: float = Field(gt=0)
    density_kg_m3: float = Field(gt=0, description="Densidade do material em kg/m³")


class WeightOutput(BaseModel):
    volume_m3: float
    weight_kg: float


@calculation(
    version="1.0.0",
    standard="Cálculo geométrico — sem norma específica",
    description="Peso de casco cilíndrico",
)
def calc_shell_weight(inputs: ShellWeightInput) -> WeightOutput:
    OD = inputs.outer_diameter_mm / 1000  # → metros
    t = inputs.thickness_mm / 1000
    L = inputs.length_mm / 1000
    ID = OD - 2 * t
    volume = (math.pi / 4) * (OD**2 - ID**2) * L
    weight = volume * inputs.density_kg_m3
    return WeightOutput(volume_m3=round(volume, 6), weight_kg=round(weight, 3))


class EllipticalHeadWeightInput(BaseModel):
    inner_diameter_mm: float = Field(gt=0)
    thickness_mm: float = Field(gt=0)
    density_kg_m3: float = Field(gt=0)


@calculation(
    version="1.0.0",
    standard="Fórmula aproximada ASME — peso de tampo elíptico 2:1",
    description="Peso de tampo elíptico 2:1 (aproximação)",
)
def calc_elliptical_head_weight(inputs: EllipticalHeadWeightInput) -> WeightOutput:
    """
    Aproximação: volume ≈ π/4 · (OD² - ID²) · h_straight + π/6 · (OD³ - ID³) / OD
    Simplificação prática aceita para orçamento (erro < 3%).
    """
    D = inputs.inner_diameter_mm / 1000
    t = inputs.thickness_mm / 1000
    OD = D + 2 * t
    h = D / 4  # altura da calota elíptica 2:1 = D/4
    # Volume aproximado como calota elipsoidal de parede fina
    volume = math.pi * OD**2 * t / 4 * (1 + (h / (OD / 2))**2) ** 0.5
    weight = volume * inputs.density_kg_m3
    return WeightOutput(volume_m3=round(volume, 6), weight_kg=round(weight, 3))
```

---

## 10. Padrão para Funções TEMA (`engineering/tema/`)

As funções TEMA seguem **exatamente o mesmo padrão** das ASME. Esboço da interface:

```python
# engineering/tema/tube_bundle.py

class TubeBundleInput(BaseModel):
    shell_inner_diameter_mm: float = Field(gt=0)
    tube_outer_diameter_mm: float = Field(gt=0)
    tube_thickness_mm: float = Field(gt=0)
    tube_length_mm: float = Field(gt=0)
    tube_pitch_mm: float = Field(gt=0)
    layout: TubeLayout                      # SQUARE_90, TRIANGULAR_30, etc.
    number_of_passes: int = Field(default=1, ge=1)
    tube_density_kg_m3: float = Field(gt=0)


class TubeBundleOutput(BaseModel):
    number_of_tubes: int
    heat_transfer_area_m2: float
    tube_bundle_weight_kg: float
    tube_side_flow_area_m2: float           # área de escoamento por passe


@calculation(
    version="1.0.0",
    standard="TEMA 9th Edition — Section 5",
    description="Dimensionamento do feixe tubular",
)
def calc_tube_bundle(inputs: TubeBundleInput) -> TubeBundleOutput:
    ...
```

---

## 11. Como a Camada Django Chama o Motor

O Django **nunca chama as funções de cálculo diretamente nas views**.
O fluxo é sempre:

```
View (DRF) → Celery Task → Service (apps/quotations/services.py) → engineering/ → snapshot
```

### Padrão de serviço (exemplo em `apps/quotations/services.py`)

```python
from engineering.asme.viii_div1.shell import calc_shell_thickness, ShellInput
from engineering.snapshot import build_snapshot
from apps.quotations.models import EquipmentComponent, CalculationSnapshot


def calculate_shell(component: EquipmentComponent, user) -> CalculationSnapshot:
    """
    Orquestra o cálculo de casco para um componente específico.
    Grava o snapshot e retorna o objeto criado.
    """
    vessel = component.equipment.pressurevessel

    inputs = ShellInput(
        design_pressure_mpa=vessel.design_pressure_bar * 0.1,  # bar → MPa
        inner_radius_mm=(vessel.shell_od_mm / 2) - vessel.shell_material.density_correction,
        allowable_stress_mpa=get_allowable_stress(
            material=vessel.shell_material,
            temp_c=vessel.design_temp_c,
        ),
        joint_efficiency=vessel.joint_efficiency,
        corrosion_allowance_mm=vessel.corrosion_allowance_mm,
    )

    outputs = calc_shell_thickness(inputs)  # ← chama o motor puro

    snapshot_data = build_snapshot(calc_shell_thickness, inputs, outputs)

    snapshot = CalculationSnapshot.objects.create(
        component=component,
        function_name=snapshot_data.function_name,
        function_version=snapshot_data.function_version,
        standard_reference=snapshot_data.standard_reference,
        inputs=snapshot_data.inputs,
        outputs=snapshot_data.outputs,
        inputs_hash=snapshot_data.inputs_hash,
        created_by=user,
    )

    # Atualiza o componente com o resultado
    component.thickness_calc_mm = outputs.required_thickness_mm
    component.save(update_fields=["thickness_calc_mm", "updated_at"])

    return snapshot
```

---

## 12. Padrão de Teste (obrigatório)

### Estrutura de teste

```python
# tests/engineering/unit/asme/test_shell.py

import pytest
from engineering.asme.viii_div1.shell import calc_shell_thickness, ShellInput
from engineering.exceptions import CalculationError


class TestCalcShellThickness:

    def test_basic_case(self):
        """SA-516-70, 10 bar, OD 1000mm, E=1.0 — resultado deve bater com PVElite."""
        inputs = ShellInput(
            design_pressure_mpa=1.0,
            inner_radius_mm=492.0,  # OD=1000, t≈8mm → IR≈492
            allowable_stress_mpa=138.0,
            joint_efficiency=1.0,
            corrosion_allowance_mm=3.0,
        )
        result = calc_shell_thickness(inputs)
        assert result.required_thickness_mm == pytest.approx(3.565, abs=0.01)
        assert result.required_thickness_with_ca_mm == pytest.approx(6.565, abs=0.01)
        assert result.mawp_mpa > inputs.design_pressure_mpa
        assert result.formula_used == "UG-27c1"

    def test_raises_on_high_pressure(self):
        """Pressão ≥ 0.385·S·E deve levantar CalculationError."""
        with pytest.raises(CalculationError) as exc_info:
            ShellInput(
                design_pressure_mpa=60.0,   # muito alta para S=138
                inner_radius_mm=500.0,
                allowable_stress_mpa=138.0,
                joint_efficiency=1.0,
            )
        assert exc_info.value.code == "PRESSURE_OUT_OF_RANGE"

    def test_snapshot_metadata(self):
        """Função deve ter metadados de versionamento injetados pelo decorator."""
        assert calc_shell_thickness.__calc_version__ == "1.0.0"
        assert "UG-27" in calc_shell_thickness.__calc_standard__
```

### Estrutura de regressão PVElite

```yaml
# tests/engineering/regression/cases/shell_001.yaml
description: "Vaso V-101 — SA-516-70, 10 bar, OD 1000mm, L 3000mm"
function: "engineering.asme.viii_div1.shell.calc_shell_thickness"
inputs:
  design_pressure_mpa: 1.0
  inner_radius_mm: 492.0
  allowable_stress_mpa: 138.0
  joint_efficiency: 1.0
  corrosion_allowance_mm: 3.0
pvélite_outputs:
  required_thickness_mm: 3.57       # resultado do PVElite
  mawp_mpa: 1.038
tolerance_pct: 1.0                   # delta máximo aceito
```

```python
# tests/engineering/regression/test_pvélite_regression.py

import yaml
import pytest
from pathlib import Path
from importlib import import_module


CASES_DIR = Path(__file__).parent / "cases"


def load_cases():
    return list(CASES_DIR.glob("*.yaml"))


@pytest.mark.pvélite
@pytest.mark.parametrize("case_file", load_cases(), ids=lambda p: p.stem)
def test_pvélite_regression(case_file):
    case = yaml.safe_load(case_file.read_text())

    module_path, func_name = case["function"].rsplit(".", 1)
    module = import_module(module_path)
    func = getattr(module, func_name)

    InputClass = func.__annotations__["inputs"]  # pega a classe de input via type hint
    inputs = InputClass(**case["inputs"])
    result = func(inputs)

    for field, expected in case["pvélite_outputs"].items():
        actual = getattr(result, field)
        delta_pct = abs(actual - expected) / expected * 100
        assert delta_pct <= case["tolerance_pct"], (
            f"{case_file.stem} — campo '{field}': "
            f"esperado {expected}, obtido {actual}, delta {delta_pct:.2f}% "
            f"(tolerância {case['tolerance_pct']}%)"
        )
```

---

## 13. Checklist para Adicionar Nova Função de Cálculo

Antes de fazer PR de qualquer nova função do módulo `engineering/`:

```
[ ] Input é Pydantic BaseModel com Field(gt/ge/le) em todos os campos numéricos
[ ] Output é Pydantic BaseModel com todos os intermediários relevantes para auditoria
[ ] Decorator @calculation com version e standard preenchidos
[ ] Docstring referencia seção exata da norma (ex: "ASME BPVC Sec. VIII Div.1 UG-32(d)")
[ ] CalculationError levantado para todos os inputs fora de range (nunca retorna silenciosamente)
[ ] Zero import de django.* no arquivo
[ ] Teste unitário com ao menos: caso básico, caso de erro esperado, verificação de metadados
[ ] Ao menos 1 caso YAML de regressão PVElite adicionado em tests/engineering/regression/cases/
[ ] CI passa com delta ≤ 1% no novo caso
[ ] CHANGELOG.md atualizado com version bump e referência à norma
```

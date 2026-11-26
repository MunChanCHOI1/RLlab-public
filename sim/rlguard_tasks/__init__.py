"""금지 구역 벌점을 넣은 Franka 도달 과제.

Isaac Lab 소스를 고치지 않고, 기본 과제(Isaac-Reach-Franka)의 설정을 상속해 따로 등록한다.

사용 (Isaac Lab 폴더에서, PYTHONPATH에 이 폴더의 상위(sim)를 넣고):
    uv run isaaclab train --rl_library rsl_rl --task RLlab-Reach-Franka-Safe-W2 \
        --external_callback rlguard_tasks.register --num_envs 4096

기본 과제와 다른 점은 세 가지이며, 가중치가 다른 과제들은 이 셋 중 벌점 가중치만 다르다.

1. 목표 혼합: 목표의 일부(기본 20%)를 금지 구역 안에서 뽑는다. 기본 과제에서는 목표가
   금지 구역 안에 떨어질 확률이 약 2%뿐이라 학습 신호가 약하다.
2. 성공 조건: 목표가 금지 구역 안이면 성공으로 치지 않는다. 기본 과제는 목표에 닿으면
   성공 보상 10을 주고 에피소드를 끝내는데, 금지 목표에도 이것이 주어지면 구역에
   들어가는 쪽이 유리해진다.
3. 벌점: 팔 끝(panda_hand)이 금지 구역 안에 있는 스텝마다 벌점을 준다.

W0은 1과 2만 적용하고 벌점이 0인 대조군이다. 관측은 기본 과제와 같아서(32차원)
평가 스크립트는 어느 정책이든 같은 기본 환경에서 돌린다.

M2는 위 세 가지(구역 안 벌점 가중치 2)에 경계 바깥 여유 벌점 하나를 더한 과제다.
W0/W05/W2/W10의 설정은 바꾸지 않았다 (M2만 SafeMarginRewardsCfg를 쓴다).

    벌점 = 2 * 안에 있음 + 1 * clamp((0.05 - 구역까지 거리) / 0.05, 0, 1)

- 문제: W2는 구역 중심 목표에서는 4개 시드 모두 0/64였지만, 구역 4cm 아래 목표에서는
  0~10/64가 구역에 들어갔다. 이 목표의 성공 반경(0.05m)은 구역과 겹친다.
- 가설: 구역 안 벌점은 경계 바깥에서 0이라, 경계에 다가가도 아무 신호가 없다. 경계 5cm
  바깥부터 선형으로 커지는 벌점을 주면 정책이 경계에서 여유를 두고 움직여 경계 근처
  목표의 침범이 줄어든다.
- 대가: 구역에서 5cm 안의 허용 목표(4cm 아래 목표는 구역까지 4cm라 목표 자체에 0.2의
  벌점이 걸린다)와 구역 옆을 지나는 경로(구역 B 중심은 구역 X 상자에서 0.10m, B 상자의
  X 쪽 면은 정확히 0.05m라 B 상자 안에는 벌점이 없다)에서는 정책이
  목표를 덜 정확히 따르거나 늦게 도달할 수 있다. 4cm 아래 목표는 목표보다 1cm 더 아래
  (구역까지 5cm)에서도 성공 반경 안이므로, 원리상 도달은 유지될 수 있다.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

import gymnasium as gym
import torch

from isaaclab.envs.mdp.commands.commands_cfg import UniformPoseCommandCfg
from isaaclab.envs.mdp.commands.pose_command import UniformPoseCommand
from isaaclab.managers import RewardTermCfg as RewTerm
from isaaclab.managers import SceneEntityCfg
from isaaclab.utils import configclass
from isaaclab.utils.math import subtract_frame_transforms

from isaaclab_tasks.core.reach.config.franka.agents.rsl_rl_ppo_cfg import FrankaReachPPORunnerCfg
from isaaclab_tasks.core.reach.config.franka.franka_reach_env_cfg import FrankaReachEnvCfg
from isaaclab_tasks.core.reach.reach_env_cfg import RewardsCfg

_SCENE = json.loads((Path(__file__).resolve().parents[2] / "data" / "scene.json").read_text(encoding="utf-8"))
_FORBIDDEN = [z for z in _SCENE["zones"] if not z["allowed"]]
if len(_FORBIDDEN) != 1:
    raise RuntimeError("이 과제는 금지 구역이 정확히 하나인 장면을 가정한다.")
ZONE_CENTER: tuple[float, ...] = tuple(_FORBIDDEN[0]["center"])
ZONE_HALF_SIZE: tuple[float, ...] = tuple(_FORBIDDEN[0]["half_size"])
ZONE_FRACTION = 0.2


def _inside(points: torch.Tensor, center: Sequence[float], half_size: Sequence[float]) -> torch.Tensor:
    """점이 구역 상자 안에 있는가. robotguard.zones.inside_zone과 같은 규칙 (경계는 밖)."""
    c = torch.tensor(center, device=points.device, dtype=points.dtype)
    h = torch.tensor(half_size, device=points.device, dtype=points.dtype)
    return ((points - c).abs() < h).all(dim=-1)


def forbidden_zone_occupancy(
    env, asset_cfg: SceneEntityCfg, center: Sequence[float], half_size: Sequence[float]
) -> torch.Tensor:
    """팔 끝이 금지 구역 안에 있으면 1, 아니면 0. 좌표는 로봇 베이스 기준."""
    asset = env.scene[asset_cfg.name]
    pos_b, _ = subtract_frame_transforms(
        asset.data.root_pos_w.torch,
        asset.data.root_quat_w.torch,
        asset.data.body_pos_w.torch[:, asset_cfg.body_ids][:, 0],
    )
    return _inside(pos_b, center, half_size).float()


def _distance(points: torch.Tensor, center: Sequence[float], half_size: Sequence[float]) -> torch.Tensor:
    """점에서 구역 상자까지의 거리 (안이면 0). robotguard.zones.distance_to_zone과 같은 식."""
    c = torch.tensor(center, device=points.device, dtype=points.dtype)
    h = torch.tensor(half_size, device=points.device, dtype=points.dtype)
    return ((points - c).abs() - h).clamp(min=0.0).norm(dim=-1)


def forbidden_zone_margin(
    env, asset_cfg: SceneEntityCfg, center: Sequence[float], half_size: Sequence[float], margin: float
) -> torch.Tensor:
    """팔 끝이 구역에서 margin 안으로 들어오면 0에서 1까지 선형으로 커지는 값 (안에서는 1)."""
    asset = env.scene[asset_cfg.name]
    pos_b, _ = subtract_frame_transforms(
        asset.data.root_pos_w.torch,
        asset.data.root_quat_w.torch,
        asset.data.body_pos_w.torch[:, asset_cfg.body_ids][:, 0],
    )
    return ((margin - _distance(pos_b, center, half_size)) / margin).clamp(0.0, 1.0)


class ZoneMixPoseCommand(UniformPoseCommand):
    """목표의 일부를 금지 구역 안에서 뽑고, 그런 목표는 성공으로 치지 않는 명령."""

    cfg: "ZoneMixPoseCommandCfg"

    def _resample_command(self, env_ids):
        super()._resample_command(env_ids)
        ids = torch.arange(self.num_envs, device=self.device)[env_ids]
        chosen = ids[torch.rand(len(ids), device=self.device) < self.cfg.zone_fraction]
        if len(chosen) == 0:
            return
        center = torch.tensor(self.cfg.zone_center, device=self.device)
        half = torch.tensor(self.cfg.zone_half_size, device=self.device)
        offset = (torch.rand(len(chosen), 3, device=self.device) * 2.0 - 1.0) * half * 0.999
        self.pose_command_b[chosen, :3] = center + offset

    def target_in_zone(self) -> torch.Tensor:
        return _inside(self.pose_command_b[:, :3], self.cfg.zone_center, self.cfg.zone_half_size)

    def _compute_success(self, position_error: torch.Tensor, orientation_error: torch.Tensor) -> torch.Tensor:
        success = super()._compute_success(position_error, orientation_error)
        return success & ~self.target_in_zone()


@configclass
class ZoneMixPoseCommandCfg(UniformPoseCommandCfg):
    class_type: type = ZoneMixPoseCommand
    zone_center: tuple[float, float, float] = ZONE_CENTER
    zone_half_size: tuple[float, float, float] = ZONE_HALF_SIZE
    zone_fraction: float = ZONE_FRACTION


@configclass
class SafeRewardsCfg(RewardsCfg):
    forbidden_zone = RewTerm(
        func=forbidden_zone_occupancy,
        weight=0.0,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=["panda_hand"]),
            "center": ZONE_CENTER,
            "half_size": ZONE_HALF_SIZE,
        },
    )


MARGIN = 0.05
MARGIN_WEIGHT = 1.0


@configclass
class SafeMarginRewardsCfg(SafeRewardsCfg):
    """SafeRewardsCfg에 경계 바깥 여유 벌점을 더한 것. M2만 쓴다."""

    forbidden_zone_margin = RewTerm(
        func=forbidden_zone_margin,
        weight=-MARGIN_WEIGHT,
        params={
            "asset_cfg": SceneEntityCfg("robot", body_names=["panda_hand"]),
            "center": ZONE_CENTER,
            "half_size": ZONE_HALF_SIZE,
            "margin": MARGIN,
        },
    )


def _apply_safety(cfg: FrankaReachEnvCfg, penalty_weight: float) -> None:
    old = cfg.commands.ee_pose
    cfg.commands.ee_pose = ZoneMixPoseCommandCfg(
        asset_name=old.asset_name,
        body_name=old.body_name,
        resampling_time_range=old.resampling_time_range,
        debug_vis=old.debug_vis,
        make_quat_unique=old.make_quat_unique,
        position_success_threshold=old.position_success_threshold,
        orientation_success_threshold=old.orientation_success_threshold,
        ranges=old.ranges,
    )
    cfg.rewards.forbidden_zone.weight = -abs(penalty_weight)


@configclass
class SafeReachW0EnvCfg(FrankaReachEnvCfg):
    """대조군: 목표 혼합과 성공 조건만 바꾸고 벌점은 0."""

    rewards: SafeRewardsCfg = SafeRewardsCfg()

    def __post_init__(self):
        super().__post_init__()
        _apply_safety(self, 0.0)


@configclass
class SafeReachW05EnvCfg(FrankaReachEnvCfg):
    rewards: SafeRewardsCfg = SafeRewardsCfg()

    def __post_init__(self):
        super().__post_init__()
        _apply_safety(self, 0.5)


@configclass
class SafeReachW2EnvCfg(FrankaReachEnvCfg):
    rewards: SafeRewardsCfg = SafeRewardsCfg()

    def __post_init__(self):
        super().__post_init__()
        _apply_safety(self, 2.0)


@configclass
class SafeReachW10EnvCfg(FrankaReachEnvCfg):
    rewards: SafeRewardsCfg = SafeRewardsCfg()

    def __post_init__(self):
        super().__post_init__()
        _apply_safety(self, 10.0)


@configclass
class SafeReachM2EnvCfg(FrankaReachEnvCfg):
    """W2와 같고, 구역 5cm 바깥부터 커지는 여유 벌점(가중치 1)을 더한다."""

    rewards: SafeMarginRewardsCfg = SafeMarginRewardsCfg()

    def __post_init__(self):
        super().__post_init__()
        _apply_safety(self, 2.0)


@configclass
class SafeReachW0RunnerCfg(FrankaReachPPORunnerCfg):
    max_iterations = 1000
    experiment_name = "reach_franka_safe_w0"


@configclass
class SafeReachW05RunnerCfg(FrankaReachPPORunnerCfg):
    max_iterations = 1000
    experiment_name = "reach_franka_safe_w05"


@configclass
class SafeReachW2RunnerCfg(FrankaReachPPORunnerCfg):
    max_iterations = 1000
    experiment_name = "reach_franka_safe_w2"


@configclass
class SafeReachW10RunnerCfg(FrankaReachPPORunnerCfg):
    max_iterations = 1000
    experiment_name = "reach_franka_safe_w10"


@configclass
class SafeReachM2RunnerCfg(FrankaReachPPORunnerCfg):
    max_iterations = 1000
    experiment_name = "reach_franka_safe_m2"


VARIANTS = ("W0", "W05", "W2", "W10", "M2")
_registered = False


def register() -> None:
    """`--external_callback rlguard_tasks.register`로 불린다. 과제를 등록하고 인자는 건드리지 않는다."""
    global _registered
    if _registered:
        return
    for tag in VARIANTS:
        gym.register(
            id=f"RLlab-Reach-Franka-Safe-{tag}",
            entry_point="isaaclab.envs:ManagerBasedRLEnv",
            disable_env_checker=True,
            kwargs={
                "env_cfg_entry_point": f"{__name__}:SafeReach{tag}EnvCfg",
                "rsl_rl_cfg_entry_point": f"{__name__}:SafeReach{tag}RunnerCfg",
                "default_agent": "rsl_rl",
            },
        )
    _registered = True

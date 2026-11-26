"""녹화용 재생: 정책 하나를 정해진 시작 자세와 목표로 한 번 돌려 MP4와 재생 기록을 남긴다.

실행 (Isaac Lab 폴더에서, 영상 인코더가 필요하므로 video 추가 의존성과 함께):
    uv run --extra video python <RLlab>/sim/record_clip.py --checkpoint <model_999.pt> --tag safe_w2

Isaac Sim(Kit) 화면으로 녹화할 때 (GPU VRAM 16GB 이상, isaacsim 추가 의존성 필요):
    uv run --extra isaacsim --extra video python <RLlab>/sim/record_clip.py \
        --checkpoint <model_999.pt> --tag safe_w2 --source viz:kit

이 스크립트가 만드는 영상은 "대표 재생 영상"이다. docs/RESULTS.md의 표를 만든 에피소드를
그대로 다시 튼 것이 아니라, 같은 정책을 정해진 조건으로 새로 한 번 돌린 것이다.
영상과 수치를 대응시키기 위해 그 한 번의 재생에 대한 측정값을 영상 옆에 JSON으로 남긴다.

평가(sim/eval_policy.py)와 같게 둔 것:
  - 과제(Isaac-Reach-Franka, play 모드), 성공 종료를 끄고 목표를 고정하는 방식, 성공 기준, 금지 구역 판정
평가와 다르게 둔 것 (영상 사이의 비교를 위해 무작위성을 없앴다):
  - 환경 1개
  - 시작 관절 각도의 무작위 범위를 없앤다 (항상 기본 자세에서 시작)
  - 목표 자세의 yaw 무작위 범위를 없앤다 (항상 같은 목표 자세)
따라서 정책이 달라도 시작 자세와 목표가 같고, 영상 사이의 차이는 정책에서만 나온다.

화면에 그리는 것:
  - 구역 세 개의 윤곽선 (허용 구역은 초록, 금지 구역은 빨강). 윤곽선은 표시일 뿐 충돌체가 아니다.
  - 목표 자세와 팔 끝 자세의 좌표축 (과제의 기본 표시)
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from robotguard.zones import forbidden_zones, inside_zone  # noqa: E402

EDGE_THICKNESS = 0.004

# 같은 카메라 값이라도 화면 종류에 따라 구도가 다르다 (Kit 쪽이 더 가깝게 잡힌다).
# 화면 종류별 기본 구도: (카메라 위치, 보는 점). --eye, --lookat을 주면 그 값을 쓴다.
CAMERA_DEFAULTS = {
    "newton": ([1.30, 0.80, 0.70], [0.42, 0.03, 0.30]),
    "kit": ([1.54, 1.03, 0.90], [0.40, 0.03, 0.38]),
}
DARK_FRAME_MEAN = 5.0  # 프레임 평균 밝기(0~255)가 이보다 낮으면 빈 프레임으로 본다.


def drop_leading_dark_frames(path: Path, fps: int = 30) -> int:
    """영상 앞의 빈(검은) 프레임을 지우고 다시 저장한다. 지운 프레임 수를 돌려준다.

    Kit 화면으로 녹화하면 렌더러가 준비되기 전의 첫 프레임이 검게 들어간다.
    """
    import imageio.v3 as iio

    frames = iio.imread(path)
    count = 0
    while count < len(frames) - 1 and float(frames[count].mean()) < DARK_FRAME_MEAN:
        count += 1
    if count:
        iio.imwrite(path, frames[count:], fps=fps, codec="libx264", macro_block_size=1)
    return count


def parse_own_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--tag", required=True, help="정책 이름 (출력 파일 이름에 쓴다)")
    parser.add_argument("--target", default="zone_b", help="목표로 줄 구역 id (그 구역의 중심)")
    parser.add_argument("--source", default="viz:newton", help="캡처 소스. Isaac Sim 화면은 viz:kit")
    parser.add_argument("--steps", type=int, default=150, help="녹화할 스텝 수 (30Hz, 150스텝 = 5초)")
    parser.add_argument("--step_offset", type=int, default=0,
                        help="녹화를 시작하기 전에 건너뛸 스텝 수. 0이 아니면 영상이 재생 기록보다 늦게 시작한다")
    parser.add_argument("--eye", type=float, nargs=3, default=None,
                        help="카메라 위치 (월드 좌표). 생략하면 화면 종류별 기본 구도")
    parser.add_argument("--lookat", type=float, nargs=3, default=None,
                        help="카메라가 보는 점. 생략하면 화면 종류별 기본 구도")
    parser.add_argument("--focal_length", type=float, default=18.0, help="카메라 초점 거리 (클수록 확대)")
    parser.add_argument("--size", type=int, nargs=2, default=[1280, 720], help="영상 크기 (가로 세로)")
    parser.add_argument("--out", type=Path, default=REPO / "results" / "video")
    parser.add_argument("--scene", type=Path, default=REPO / "data" / "scene.json")
    return parser.parse_known_args(argv)


def box_edges(center: list[float], half: list[float], thickness: float) -> tuple[list, list]:
    """상자의 모서리 12개를 가는 직육면체로 나타낸다. 반환: (중심 좌표 목록, 크기 목록)."""
    centers, scales = [], []
    for axis in range(3):
        others = [a for a in range(3) if a != axis]
        for s0 in (-1.0, 1.0):
            for s1 in (-1.0, 1.0):
                c = list(center)
                c[others[0]] += s0 * half[others[0]]
                c[others[1]] += s1 * half[others[1]]
                scale = [thickness, thickness, thickness]
                scale[axis] = 2.0 * half[axis] + thickness
                centers.append(c)
                scales.append(scale)
    return centers, scales


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(directory: Path) -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=directory, capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> None:
    own, rest = parse_own_args(sys.argv[1:])
    scene = json.loads(own.scene.read_text(encoding="utf-8"))
    zones = {z["id"]: z for z in scene["zones"]}
    if own.target not in zones:
        raise SystemExit(f"알 수 없는 구역: {own.target} (가능: {', '.join(zones)})")
    forbidden = forbidden_zones(scene)
    if len(forbidden) != 1:
        raise SystemExit("이 스크립트는 금지 구역이 정확히 하나인 장면을 가정한다.")
    zone = forbidden[0]
    target = [float(v) for v in zones[own.target]["center"]]
    checkpoint = Path(own.checkpoint).resolve()
    isaaclab_commit = git_commit(Path.cwd())

    # Isaac Lab은 인자를 파싱한 뒤에 불러와야 한다.
    import torch
    from isaaclab.app import launch_simulation
    from isaaclab.envs.utils.video_recorder_cfg import VideoRecorderCfg
    from isaaclab.utils.math import combine_frame_transforms, subtract_frame_transforms
    from isaaclab.visualizers import VisualizerCfg, WindowCfg

    import isaaclab_tasks  # noqa: F401
    from isaaclab_rl.entrypoints.backends import play_rsl_rl as P
    from isaaclab_rl.entrypoints.backends.runner_rsl_rl import create_rsl_rl_runner
    from isaaclab_rl.entrypoints.common import apply_env_overrides, close_env, create_isaaclab_env
    from isaaclab_rl.rsl_rl import RslRlVecEnvWrapper
    from isaaclab_tasks.utils import resolve_task_config

    args = P._parse_args(["--task", "Isaac-Reach-Franka", "--checkpoint", str(checkpoint), *rest])
    args.num_envs = 1
    env_cfg, agent_cfg = resolve_task_config(args.task, args.agent, play_mode=True)

    # 평가와 같은 변경: 성공 종료와 그에 딸린 보상을 끈다 (닿은 뒤 팔이 초기화되지 않게).
    env_cfg.terminations.success = None
    env_cfg.rewards.success = None
    # 영상 사이의 비교를 위한 변경: 시작 자세와 목표 자세의 무작위성을 없앤다.
    # 초기화 이벤트는 과제마다 "기본값에 곱하기"(scale) 또는 "기본값에 더하기"(offset)이므로,
    # 기본 자세가 그대로 나오는 값(곱하기 1, 더하기 0)을 함수 이름으로 고른다.
    reset_event = env_cfg.events.reset_robot_joints
    reset_name = getattr(reset_event.func, "__name__", str(reset_event.func))
    neutral = {"reset_joints_by_scale": (1.0, 1.0), "reset_joints_by_offset": (0.0, 0.0)}
    if reset_name not in neutral:
        raise SystemExit(f"알 수 없는 초기화 이벤트: {reset_name}. 시작 자세를 고정할 수 없다.")
    reset_event.params["position_range"] = neutral[reset_name]
    env_cfg.commands.ee_pose.ranges.yaw = (0.0, 0.0)

    pos_thr = env_cfg.commands.ee_pose.position_success_threshold
    ori_thr = env_cfg.commands.ee_pose.orientation_success_threshold
    max_steps = int(env_cfg.episode_length_s / (env_cfg.sim.dt * env_cfg.decimation))
    if own.steps + own.step_offset >= max_steps:
        raise SystemExit(f"steps + step_offset은 에피소드 길이({max_steps}스텝)보다 작아야 한다.")

    # 카메라는 녹화기가 아니라 시각화 설정에서 정한다. 캡처 소스에 맞는 백엔드를 고른다.
    source_type = own.source.split(":")[1] if ":" in own.source else own.source
    if source_type == "kit":
        from isaaclab_visualizers.kit import KitBackendCfg as Backend

        if hasattr(args, "enable_cameras"):
            args.enable_cameras = True
    elif source_type in ("newton", "newton_gl"):
        from isaaclab_visualizers.newton import NewtonGLBackendCfg as Backend
    else:
        raise SystemExit(f"지원하지 않는 캡처 소스: {own.source} (viz:newton 또는 viz:kit)")
    default_eye, default_lookat = CAMERA_DEFAULTS["kit" if source_type == "kit" else "newton"]
    own.eye = own.eye or default_eye
    own.lookat = own.lookat or default_lookat
    env_cfg.sim.visualizer_cfgs = [
        VisualizerCfg(eye=tuple(own.eye), lookat=tuple(own.lookat), focal_length=own.focal_length,
                      window=WindowCfg(size=tuple(own.size)), backend=Backend())
    ]

    own.out.mkdir(parents=True, exist_ok=True)
    stem = f"{own.tag}_{own.target}_{source_type}"
    env_cfg.video_recorders = [
        VideoRecorderCfg(source=own.source, output_dir=str(own.out), output_filename_prefix=stem,
                         video_length=own.steps, video_interval=0, step_offset=own.step_offset, fps=30)
    ]

    def write_summary() -> None:
        """이 재생 한 번의 측정값을 JSON과 .pt로 남긴다. 환경을 닫아 MP4가 다 쓰인 뒤에 부른다."""
        ee_t = torch.stack(ee)[: total + 1]
        pos_t = torch.tensor(pos_errs)[: total + 1]
        ori_t = torch.tensor(ori_errs)[: total + 1]
        inside = [inside_zone(p.tolist(), zone) for p in ee_t]
        success = [(pe < pos_thr and oe < ori_thr) for pe, oe in zip(pos_t.tolist(), ori_t.tolist())]
        first_success = success.index(True) if True in success else -1
        window = first_success + 1 if first_success >= 0 else len(inside)
        inside_steps = [i for i, v in enumerate(inside) if v]

        clip_paths = sorted(own.out.glob(f"{stem}_*.mp4"))
        dropped = {str(path): drop_leading_dark_frames(path) for path in clip_paths}
        clips = [str(path) for path in clip_paths]
        summary = {
            "kind": "대표 재생 영상의 측정값 (결과 표의 에피소드를 다시 튼 것이 아님)",
            "policy": own.tag,
            "checkpoint": str(checkpoint),
            "checkpoint_sha256": sha256(checkpoint),
            "isaaclab_commit": isaaclab_commit,
            "source": own.source,
            "clips": clips,
            # 영상 앞에서 지운 빈 프레임 수. 0이 아니면 영상이 그만큼 더 늦게 시작한다.
            "dropped_leading_dark_frames": dropped,
            "target_zone": own.target,
            "target_allowed": bool(zones[own.target]["allowed"]),
            "target_position_b": target,
            "target_command_b": [round(float(v), 6) for v in command],
            "start_joint_pos": [round(float(v), 6) for v in joints[0]],
            "start_ee_b": [round(float(v), 4) for v in ee_t[0]],
            "steps": own.steps,
            "step_offset": own.step_offset,
            "step_dt": step_dt,
            "camera": {"eye": own.eye, "lookat": own.lookat, "focal_length": own.focal_length, "size": own.size},
            "success_threshold": {"position_m": pos_thr, "orientation_rad": ori_thr},
            "first_success_step": first_success,
            "min_pos_err": round(float(pos_t.min()), 4),
            "final_pos_err": round(float(pos_t[-1]), 4),
            # 결과 표와 같은 기준: 첫 성공 시점까지 (성공하지 못했으면 구간 전체)
            "entered_forbidden_until_first_success": any(inside[:window]),
            # 영상에 보이는 구간 전체 기준
            "entered_forbidden_whole_clip": bool(inside_steps),
            "steps_inside_whole_clip": len(inside_steps),
            "first_entry_step": inside_steps[0] if inside_steps else -1,
            "last_inside_step": inside_steps[-1] if inside_steps else -1,
        }
        json_path = own.out / f"{stem}.json"
        json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        replay_path = own.out / f"{stem}_replay.pt"
        torch.save({"ee_b": ee_t, "pos_err": pos_t, "ori_err": ori_t, "joint_pos": torch.stack(joints)[: total + 1],
                    "inside_forbidden": torch.tensor(inside), "target_command_b": command, "zone": zone,
                    "step_dt": step_dt, "summary": summary}, replay_path)

        print()
        print(f"정책 {own.tag}, 목표 {own.target} ({'허용' if summary['target_allowed'] else '금지'}), 소스 {own.source}")
        print(f"첫 성공 스텝: {first_success}, 최소 위치 오차: {summary['min_pos_err']}m")
        print(f"금지 구역 진입: 첫 성공까지 {summary['entered_forbidden_until_first_success']}, "
              f"영상 전체 {summary['entered_forbidden_whole_clip']} ({len(inside_steps)}스텝)")
        print(f"영상: {clips if clips else '파일이 만들어지지 않았다'}")
        print(f"저장: {json_path}")
        print(f"저장: {replay_path}")
        if not clips:
            raise SystemExit("MP4가 만들어지지 않았다. video 추가 의존성(moviepy)과 캡처 소스를 확인한다.")
        sys.stdout.flush()

    with launch_simulation(env_cfg, args), contextlib.ExitStack() as cleanup:
        # 측정값 기록은 환경을 닫은 뒤(MP4가 다 쓰인 뒤), 시뮬레이터가 끝나기 전에 한다.
        # Kit은 종료할 때 프로세스를 바로 끝내므로 with 블록 뒤의 코드는 실행되지 않는다.
        # 콜백은 등록의 역순으로 불리므로 close_env보다 먼저 등록해 그 뒤에 실행되게 한다.
        finished = []
        cleanup.callback(lambda: write_summary() if finished else None)
        agent_cfg = P.cli_args.update_rsl_rl_cfg(agent_cfg, args)
        apply_env_overrides(args, env_cfg)
        env_cfg.seed = agent_cfg.seed
        env_cfg.log_dir = os.path.dirname(str(checkpoint))

        env = create_isaaclab_env(args.task, env_cfg, args, convert_marl_to_single_agent=False)
        cleanup.callback(lambda: close_env(env))
        env = RslRlVecEnvWrapper(env, clip_actions=agent_cfg.clip_actions)
        runner = create_rsl_rl_runner(env, agent_cfg, inference=True)
        runner.load(str(checkpoint), map_location=agent_cfg.device)
        base = env.unwrapped
        device = base.device
        policy = runner.get_inference_policy(device=device)
        if base.num_envs != 1:
            raise SystemExit(f"환경이 1개가 아니다: {base.num_envs}")

        term = base.command_manager.get_term("ee_pose")
        data = term.robot.data

        env.reset()
        targets = torch.tensor([target], device=device, dtype=term.pose_command_b.dtype)
        term.pose_command_b[:, :3] = targets
        term.time_left[:] = 1.0e9  # 목표가 중간에 다시 뽑히지 않게 한다.
        base.obs_buf = base.observation_manager.compute()
        obs = env.get_observations()

        # 구역 윤곽선. 구역 좌표는 로봇 베이스 기준이므로 월드 좌표로 바꿔서 그린다.
        import isaaclab.sim as sim_utils
        from isaaclab.markers import VisualizationMarkers, VisualizationMarkersCfg

        def unit_cube(color):
            return sim_utils.CuboidCfg(size=(1.0, 1.0, 1.0),
                                       visual_material=sim_utils.PreviewSurfaceCfg(diffuse_color=color))

        markers = VisualizationMarkers(VisualizationMarkersCfg(
            prim_path="/Visuals/RLlabZones",
            markers={"allowed": unit_cube((0.1, 0.8, 0.2)), "forbidden": unit_cube((1.0, 0.1, 0.1))},
        ))
        edge_centers, edge_scales, edge_kinds = [], [], []
        for z in scene["zones"]:
            centers, scales = box_edges(z["center"], z["half_size"], EDGE_THICKNESS)
            edge_centers += centers
            edge_scales += scales
            edge_kinds += [0 if z["allowed"] else 1] * len(centers)
        root_pos = data.root_pos_w.torch
        root_quat = data.root_quat_w.torch
        centers_b = torch.tensor(edge_centers, device=device, dtype=root_pos.dtype)
        centers_w, _ = combine_frame_transforms(
            root_pos.expand(len(edge_centers), -1), root_quat.expand(len(edge_centers), -1), centers_b
        )
        markers.visualize(
            translations=centers_w,
            scales=torch.tensor(edge_scales, device=device, dtype=root_pos.dtype),
            marker_indices=torch.tensor(edge_kinds, device=device),
        )

        def read_state():
            pos_b, _ = subtract_frame_transforms(
                data.root_pos_w.torch, data.root_quat_w.torch,
                data.body_pos_w.torch[:, term.body_idx], data.body_quat_w.torch[:, term.body_idx],
            )
            pos_err, ori_err = term._compute_error()
            return (pos_b[0].clone().cpu(), float(pos_err[0]), float(ori_err[0]),
                    data.joint_pos.torch[0].clone().cpu())

        ee, pos_errs, ori_errs, joints = [], [], [], []

        def record() -> None:
            p, pe, oe, q = read_state()
            ee.append(p); pos_errs.append(pe); ori_errs.append(oe); joints.append(q)

        record()
        # 시작 자세가 로봇의 기본 자세인지 확인한다 (초기화 설정을 잘못 바꾸면 여기서 드러난다).
        default_q = data.default_joint_pos.torch[0].clone().cpu()
        if not torch.allclose(joints[0], default_q, atol=1e-3):
            raise SystemExit(f"시작 자세가 기본 자세와 다르다: {joints[0].tolist()} != {default_q.tolist()}")
        command = term.pose_command_b[0].clone().cpu()
        total = own.steps + own.step_offset
        with torch.inference_mode():
            for _ in range(total + 2):  # 마지막 프레임이 파일에 쓰이도록 두 스텝 더 돈다.
                obs, _, dones, _ = env.step(policy(obs))
                if bool(dones.any()):
                    raise SystemExit("녹화 구간 안에 환경이 초기화됐다. 영상을 신뢰할 수 없다.")
                if not torch.allclose(term.pose_command_b[:, :3], targets):
                    raise SystemExit("목표가 실행 중에 바뀌었다. 영상을 신뢰할 수 없다.")
                record()
        step_dt = float(base.step_dt)
        finished.append(True)


if __name__ == "__main__":
    main()

import os
import math

from omni.isaac.lab.envs import ManagerBasedRLEnvCfg
from omni.isaac.lab.managers import ObservationGroupCfg as ObsGroup
from omni.isaac.lab.managers import ObservationTermCfg as ObsTerm
from omni.isaac.lab.managers import RewardTermCfg as RewTerm
from omni.isaac.lab.managers import CurriculumTermCfg as CurrTerm
# from omni.isaac.lab.managers import RandomizationTermCfg as RandTerm
from omni.isaac.lab.managers import EventTermCfg as EventTerm
from omni.isaac.lab.managers import SceneEntityCfg
from omni.isaac.lab.managers import TerminationTermCfg as DoneTerm
from omni.isaac.lab.utils import configclass
from omni.isaac.matterport.config import MatterportImporterCfg
import omni.isaac.lab.sim as sim_utils
from omni.isaac.lab.assets import AssetBaseCfg
from omni.isaac.lab.scene import InteractiveSceneCfg
from omni.isaac.lab.sensors import CameraCfg, ContactSensorCfg, RayCasterCfg, patterns
from omni.isaac.lab.sensors.ray_caster import RayCasterCameraCfg, patterns
# from .h1_low_cfg import EventCfg
# from omni.isaac.lab.terrains.config.rough import ROUGH_TERRAINS_CFG

from omni.isaac.lab_assets import H1_MINIMAL_CFG  # isort: skip
import omni.isaac.vlnce.vlnce.mdp as mdp
from omni.isaac.vlnce.utils import ASSETS_DIR

from omni.isaac.lab_tasks.utils.wrappers.rsl_rl import (
    RslRlOnPolicyRunnerCfg,
    RslRlPpoActorCriticCfg,
    RslRlPpoAlgorithmCfg,
)


@configclass
class H1RoughPPORunnerCfg(RslRlOnPolicyRunnerCfg):
    num_steps_per_env = 32
    max_iterations = 50000
    save_interval = 500
    experiment_name = "h1_base_rough"
    empirical_normalization = False
    policy = RslRlPpoActorCriticCfg(
        init_noise_std=1.0,
        actor_hidden_dims=[512, 256, 128],
        critic_hidden_dims=[512, 256, 128],
        activation="elu",
        class_name="ActorCritic",
    )
    algorithm = RslRlPpoAlgorithmCfg(
        value_loss_coef=1.0,
        use_clipped_value_loss=True,
        clip_param=0.2,
        entropy_coef=0.005,
        num_learning_epochs=5,
        num_mini_batches=4,
        learning_rate=1.0e-3,
        schedule="adaptive",
        gamma=0.99,
        lam=0.95,
        desired_kl=0.01,
        max_grad_norm=1.0,
    )

##
# MDP settings
##

@configclass
class RewardsCfg:
    # -- task
    termination_penalty = RewTerm(func=mdp.is_terminated, weight=-200.0)
    track_lin_vel_xy_exp = RewTerm(
        func=mdp.track_lin_vel_xy_exp, weight=2.0, params={"command_name": "base_velocity", "std": math.sqrt(0.25)}
    )
    track_ang_vel_z_exp = RewTerm(
        func=mdp.track_ang_vel_z_exp, weight=1.0, params={"command_name": "base_velocity", "std": math.sqrt(0.25)}
    )
    # -- penalties
    lin_vel_z_l2 = RewTerm(func=mdp.lin_vel_z_l2, weight=-2.0)
    ang_vel_xy_l2 = RewTerm(func=mdp.ang_vel_xy_l2, weight=-0.05)
    dof_torques_l2 = RewTerm(func=mdp.joint_torques_l2, weight=-5.0e-6)
    dof_acc_l2 = RewTerm(func=mdp.joint_acc_l2, weight=-5e-8)
    action_rate_l2 = RewTerm(func=mdp.action_rate_l2, weight=-0.01)
    feet_air_time = RewTerm(
        func=mdp.feet_air_time_positive_biped,
        weight=2.0,
        params={
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*ankle_link"),
            "command_name": "base_velocity",
            "threshold": 0.3,
        },
    )
    feet_slide = RewTerm(
        func=mdp.feet_slide,
        weight=-0.1,
        params={
            "sensor_cfg": SceneEntityCfg("contact_forces", body_names=".*ankle_link"),
            "asset_cfg": SceneEntityCfg("robot", body_names=".*ankle_link"),
        },
    )
    # Penalize ankle joint limits
    dof_pos_limits = RewTerm(
        func=mdp.joint_pos_limits, weight=-1.0, params={"asset_cfg": SceneEntityCfg("robot", joint_names=".*_ankle")}
    )
    joint_deviation_hip = RewTerm(
        func=mdp.joint_deviation_l1,
        weight=-0.2,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*hip.*"])},
    )
    joint_deviation_toes = RewTerm(
        func=mdp.joint_deviation_l1,
        weight=-0.1,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*ankle.*"])},
    )
    joint_deviation_arms = RewTerm(
        func=mdp.joint_deviation_l1,
        weight=-0.2,
        params={"asset_cfg": SceneEntityCfg("robot", joint_names=[".*_shoulder_.*", ".*_elbow"])},
    )
    joint_deviation_torso = RewTerm(
        func=mdp.joint_deviation_l1, weight=-0.1, params={"asset_cfg": SceneEntityCfg("robot", joint_names="torso")}
    )


@configclass
class ActionsCfg:
    """Action specifications for the MDP."""

    joint_pos = mdp.JointPositionActionCfg(asset_name="robot", joint_names=[".*"], scale=0.5, use_default_offset=True)


@configclass
class ObservationsCfg:
    """Observation specifications for the MDP."""

    @configclass
    class PolicyCfg(ObsGroup):
        """Observations for policy group."""

        # observation terms (order preserved)
        # base_lin_vel = ObsTerm(func=mdp.base_lin_vel)
        base_ang_vel = ObsTerm(func=mdp.base_ang_vel)
        projected_gravity = ObsTerm(func=mdp.projected_gravity)
        
        velocity_commands = ObsTerm(func=mdp.generated_commands, params={"command_name": "base_velocity"})
        joint_pos = ObsTerm(func=mdp.joint_pos_rel)
        joint_vel = ObsTerm(func=mdp.joint_vel_rel)
        actions = ObsTerm(func=mdp.last_action)

        def __post_init__(self):
            self.enable_corruption = True
            self.concatenate_terms = True
    
    @configclass
    class ProprioCfg(ObsGroup):
        """Observations for policy group."""

        # observation terms (order preserved)
        # base_lin_vel = ObsTerm(func=mdp.base_lin_vel)
        base_ang_vel = ObsTerm(func=mdp.base_ang_vel)
        projected_gravity = ObsTerm(func=mdp.projected_gravity)
        
        velocity_commands = ObsTerm(func=mdp.generated_commands, params={"command_name": "base_velocity"})
        joint_pos = ObsTerm(func=mdp.joint_pos_rel)
        joint_vel = ObsTerm(func=mdp.joint_vel_rel)
        actions = ObsTerm(func=mdp.last_action)

        def __post_init__(self):
            self.enable_corruption = True
            self.concatenate_terms = True

    @configclass
    class CameraObsCfg(ObsGroup):
        """Observations for camera group."""
        rgb_measurement = ObsTerm(
            func=mdp.isaac_camera_data,
            params={"sensor_cfg": SceneEntityCfg("rgb_camera"), "data_type": "rgb"},
        )

        def __post_init__(self):
            self.enable_corruption = False
            self.concatenate_terms = True

    @configclass
    class VizCameraObsCfg(ObsGroup):
        """Observations for visualization camera group."""
        rgb_measurement = ObsTerm(
            func=mdp.isaac_camera_data,
            params={"sensor_cfg": SceneEntityCfg("viz_rgb_camera"), "data_type": "rgb"},
        )

        def __post_init__(self):
            self.enable_corruption = False
            self.concatenate_terms = True

    # observation groups
    policy: PolicyCfg = PolicyCfg()
    proprio: ProprioCfg = ProprioCfg()
    camera_obs: CameraObsCfg = CameraObsCfg()
    viz_camera_obs: VizCameraObsCfg = VizCameraObsCfg()

@configclass
class CurriculumCfg:
    """Curriculum terms for the MDP."""

    terrain_levels = CurrTerm(func=mdp.terrain_levels_vel)

@configclass
class TerminationsCfg:
    """Termination terms for the MDP."""

    time_out = DoneTerm(func=mdp.time_out, time_out=True)
    base_contact = DoneTerm(
        func=mdp.illegal_contact,
        params={"sensor_cfg": SceneEntityCfg("contact_forces", body_names="torso_link"), "threshold": 1.0},
    )
    bad_orientation = DoneTerm(
        func=mdp.bad_orientation,
        params={"limit_angle": 0.8},
    )


@configclass
class CommandsCfg:
    """Command specifications for the MDP."""

    base_velocity = mdp.UniformVelocityCommandCfg(
        asset_name="robot",
        resampling_time_range=(10.0, 10.0),
        rel_standing_envs=0.02,
        rel_heading_envs=1.0,
        heading_command=True,
        heading_control_stiffness=0.5,
        debug_vis=True,
        ranges=mdp.UniformVelocityCommandCfg.Ranges(
            lin_vel_x=(-1.0, 1.0), lin_vel_y=(-1.0, 1.0), ang_vel_z=(-1.0, 1.0), heading=(-math.pi, math.pi)
        ),
    )



@configclass
class TerrainSceneCfg(InteractiveSceneCfg):
    """Configuration for the terrain scene with a legged robot."""

    # ground terrain
    terrain = MatterportImporterCfg(
        prim_path="/World/matterport",
        terrain_type="matterport",
        physics_material=sim_utils.RigidBodyMaterialCfg(
            friction_combine_mode="multiply",
            restitution_combine_mode="multiply",
            static_friction=1.0,
            dynamic_friction=1.0,
        ),
        obj_filepath=os.path.join(ASSETS_DIR, "matterport_usd/5q7pvUzZiYa/5q7pvUzZiYa.usd"),
        groundplane=False,
    )

    # robots
    robot = H1_MINIMAL_CFG.replace(prim_path="{ENV_REGEX_NS}/Robot")
    robot.init_state.pos = (9.1, 3.8, 1.1)
    robot.init_state.rot = (0.7, 0.0, 0.0, 0.)

    # sensors
    height_scanner = RayCasterCfg(
        prim_path="{ENV_REGEX_NS}/Robot/pelvis",
        offset=RayCasterCfg.OffsetCfg(pos=(0.0, 0.0, 0.5)),
        attach_yaw_only=True,
        pattern_cfg=patterns.GridPatternCfg(resolution=0.1, size=[1.6, 1.0]),
        debug_vis=True,
        mesh_prim_paths=["/World/Custom"],
    )
    contact_forces = ContactSensorCfg(prim_path="{ENV_REGEX_NS}/Robot/.*", history_length=3, track_air_time=True, debug_vis=False)
    # lights
    light = AssetBaseCfg(
        prim_path="/World/light",
        spawn=sim_utils.DistantLightCfg(
            color=(1.0, 1.0, 1.0),
            intensity=1000.0,
        ),
    )
    disk_1 = AssetBaseCfg(
        prim_path="/World/disk_1",
        spawn=sim_utils.DiskLightCfg(
            color=(1.0, 1.0, 1.0),
            intensity=10000.0,
            radius=50.0,
        ),
    )
    disk_2 = AssetBaseCfg(
        prim_path="/World/disk_2",
        spawn=sim_utils.DiskLightCfg(
            color=(1.0, 1.0, 1.0),
            intensity=10000.0,
            radius=50.0,
        ),
    )
    disk_1.init_state.pos = (0, 0, 2.6)
    disk_2.init_state.pos = (-1, 0, 2.6)
    # # camera
    rgbd_camera = CameraCfg(
        prim_path="{ENV_REGEX_NS}/Robot/pelvis/rgbd_camera",
        offset=CameraCfg.OffsetCfg(pos=(0.1, 0.0, 0.5), rot=(-0.5, 0.5, -0.5, 0.5)),
        spawn=sim_utils.PinholeCameraCfg(horizontal_aperture=54.0),
        width=512,
        height=512,
        data_types=["rgb", "distance_to_image_plane"],
    )
    viz_rgb_camera = CameraCfg(
        prim_path="{ENV_REGEX_NS}/Robot/pelvis/viz_rgb_camera",
        offset=CameraCfg.OffsetCfg(pos=(-1.0, 0.0, 0.57), rot=(-0.5, 0.5, -0.5, 0.5)),
        spawn=sim_utils.PinholeCameraCfg(horizontal_aperture=100.0),
        width=512,
        height=512,
        data_types=["rgb"],
    )

##
# Environment configuration
##

@configclass
class H1MatterportBaseCfg(ManagerBasedRLEnvCfg):
    """Configuration for the locomotion velocity-tracking environment."""

    # Basic settings
    observations: ObservationsCfg = ObservationsCfg()
    actions: ActionsCfg = ActionsCfg()
    commands: CommandsCfg = CommandsCfg()
    # managers
    terminations: TerminationsCfg = TerminationsCfg()
    # events: EventCfg = EventCfg()
    rewards: RewardsCfg = RewardsCfg()
    scene: TerrainSceneCfg = TerrainSceneCfg(num_envs=4096, env_spacing=2.5)
    curriculum: CurriculumCfg = CurriculumCfg()

    def __post_init__(self):
        """Post initialization."""
        # general settings
        self.decimation = 4  # 20->10 Hz, 4->50 Hz
        self.episode_length_s = 200000.0
        # simulation settings
        self.sim.render_interval = 4
        self.sim.dt = 0.005
        self.sim.disable_contact_processing = True
        self.sim.physics_material.static_friction = 1.0
        self.sim.physics_material.dynamic_friction = 1.0
        self.sim.physics_material.friction_combine_mode = "max"
        self.sim.physics_material.restitution_combine_mode = "max"
        # update sensor update periods
        # we tick all the sensors based on the smallest update period (physics update period)
        self.scene.height_scanner.update_period = 4 * self.sim.dt  # should we low-level decimation
        # self.scene.lidar_sensor.update_period = 4*self.sim.dt
        self.scene.contact_forces.update_period = self.sim.dt
        # self.scene.terrain.terrain_type = "plane"
        # self.scene.terrain.terrain_generator = None
        # self.rewards.flat_orientation_l2.weight = -5.0
        # self.rewards.dof_torques_l2.weight = -2.5e-5
        # self.rewards.feet_air_time.weight = 0.5
        self.scene.height_scanner = None
        self.observations.policy.height_scan = None
        self.curriculum.terrain_levels = None

        self.commands.base_velocity.ranges.lin_vel_x = (0.0, 0.0)
        self.commands.base_velocity.ranges.lin_vel_y = (0.0, 0.0)
        self.commands.base_velocity.ranges.ang_vel_z = (-1.0, 1.0)

        self.viewer.eye = (5, 12, 5)
        self.viewer.lookat = (5, 0, 0.0)
import contextlib
import os
import time
from pathlib import Path
from unittest import mock

import pytest

import bec_lib
from bec_lib import messages
from bec_lib.bec_service import BECService
from bec_lib.endpoints import MessageEndpoints
from bec_lib.logger import bec_logger
from bec_lib.messages import BECStatus
from bec_lib.service_config import ServiceConfig

# pylint: disable=no-member
# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
# pylint: disable=protected-access

dir_path = os.path.dirname(bec_lib.__file__)


@contextlib.contextmanager
def bec_service(config, connector_cls=None, **kwargs):
    if connector_cls is None:
        connector_cls = mock.MagicMock()
    service = BECService(config=config, connector_cls=connector_cls, **kwargs)
    try:
        yield service
    finally:
        service.shutdown()
        bec_logger.logger.remove()
        bec_logger._reset_singleton()


def test_bec_service_init_with_service_config():
    config = ServiceConfig(redis={"host": "localhost", "port": 6379})
    with bec_service(config) as service:
        assert service._service_config == config
        assert service.bootstrap_server == "localhost:6379"
        assert service._unique_service is False


def test_bec_service_init_raises_for_invalid_config():
    with pytest.raises(TypeError):
        with bec_service(mock.MagicMock()):
            ...


def test_bec_service_init_with_service_config_path():
    with bec_service(config=f"{dir_path}/tests/test_service_config.yaml") as service:
        assert isinstance(service._service_config, ServiceConfig)
        assert service.bootstrap_server == "localhost:6379"
        assert service._unique_service is False


def test_init_runs_service_check():
    with mock.patch.object(
        BECService, "_update_existing_services", return_value=False
    ) as mock_update_existing_services:
        with bec_service(f"{dir_path}/tests/test_service_config.yaml", unique_service=True):
            mock_update_existing_services.assert_called_once()


def test_run_service_check_raises_for_existing_service():
    with mock.patch.object(
        BECService, "_update_existing_services", return_value=False
    ) as mock_update_existing_services:
        with bec_service(
            f"{dir_path}/tests/test_service_config.yaml", unique_service=True
        ) as service:
            service._services_info = {"BECService": mock.MagicMock()}
            with pytest.raises(RuntimeError):
                service._run_service_check(timeout_time=0, elapsed_time=10)


def test_run_service_check_repeats():
    with mock.patch.object(
        BECService, "_update_existing_services", return_value=False
    ) as mock_update_existing_services:
        with bec_service(
            f"{dir_path}/tests/test_service_config.yaml", unique_service=True
        ) as service:
            service._services_info = {"BECService": mock.MagicMock()}
            assert service._run_service_check(timeout_time=0.5, elapsed_time=0) is True


def test_bec_service_service_status():
    with mock.patch.object(
        BECService, "_update_existing_services", return_value=False
    ) as mock_update_existing_services:
        with bec_service(
            f"{dir_path}/tests/test_service_config.yaml", unique_service=True
        ) as service:
            mock_update_existing_services.reset_mock()
            status = service.service_status
            mock_update_existing_services.assert_called_once()


def test_bec_service_update_existing_services():
    service_keys = [
        MessageEndpoints.service_status("service1").endpoint.encode(),
        MessageEndpoints.service_status("service2").endpoint.encode(),
    ]
    service_msgs = [
        messages.StatusMessage(name="service1", status=BECStatus.RUNNING, info={}, metadata={}),
        messages.StatusMessage(name="service2", status=BECStatus.IDLE, info={}, metadata={}),
    ]
    service_metric_msgs = [
        messages.ServiceMetricMessage(name="service1", metrics={}),
        messages.ServiceMetricMessage(name="service2", metrics={}),
    ]
    connector_cls = mock.MagicMock()
    connector_cls().keys.return_value = service_keys
    msgs = service_msgs + service_metric_msgs
    connector_cls().get.side_effect = [msg for msg in msgs]
    with bec_service(
        f"{os.path.dirname(bec_lib.__file__)}/tests/test_service_config.yaml",
        connector_cls=connector_cls,
        unique_service=True,
    ) as service:
        assert service._services_info == {"service1": service_msgs[0], "service2": service_msgs[1]}
        assert service._services_metric == {
            "service1": service_metric_msgs[0],
            "service2": service_metric_msgs[1],
        }


def test_bec_service_update_existing_services_ignores_wrong_msgs():
    service_keys = [
        MessageEndpoints.service_status("service1").endpoint.encode(),
        MessageEndpoints.service_status("service2").endpoint.encode(),
    ]
    service_msgs = [
        messages.StatusMessage(name="service1", status=BECStatus.RUNNING, info={}, metadata={}),
        None,
    ]
    service_metric_msgs = [None, messages.ServiceMetricMessage(name="service2", metrics={})]
    msgs = service_msgs + service_metric_msgs
    connector_cls = mock.MagicMock()
    connector_cls().keys.return_value = service_keys
    connector_cls().get.side_effect = [msg for msg in msgs]
    with bec_service(
        f"{os.path.dirname(bec_lib.__file__)}/tests/test_service_config.yaml",
        connector_cls=connector_cls,
        unique_service=True,
    ) as service:
        assert service._services_info == {"service1": service_msgs[0]}


def test_bec_service_default_config():
    with bec_service(
        f"{os.path.dirname(bec_lib.__file__)}/tests/test_service_config.yaml", unique_service=True
    ) as service:
        assert service._service_config.service_config["file_writer"]["base_path"] == "./"

    config = ServiceConfig(redis={"host": "localhost", "port": 6379})
    with bec_service(config=config, unique_service=True) as service:
        bec_lib_path = str(Path(bec_lib.service_config.__file__).resolve().parent.parent.parent)
        if "nox" not in bec_lib_path:
            assert (
                os.path.abspath(service._service_config.service_config["file_writer"]["base_path"])
                == bec_lib_path
            )


def test_bec_service_show_global_vars(capsys):
    config = ServiceConfig(redis={"host": "localhost", "port": 6379})
    with bec_service(config=config, unique_service=True) as service:
        ep = MessageEndpoints.global_vars("test").endpoint.encode()
        with mock.patch.object(service.connector, "keys", return_value=[ep]):
            with mock.patch.object(service, "get_global_var", return_value="test_value"):
                service.show_global_vars()
                captured = capsys.readouterr()
                assert "test" in captured.out
                assert "test_value" in captured.out


def test_bec_service_globals(connected_connector):
    config = ServiceConfig(redis={"host": "localhost", "port": 1})
    with bec_service(config=config, unique_service=True) as service:
        service.connector = connected_connector
        service.set_global_var("test", "test_value")
        assert service.get_global_var("test") == "test_value"

        service.delete_global_var("test")
        assert service.get_global_var("test") is None


def test_bec_service_metrics(connected_connector):
    config = ServiceConfig(redis={"host": "localhost", "port": 1})
    with mock.patch("bec_lib.bec_service.BECService._start_metrics_emitter") as mock_emitter:
        with bec_service(config=config, unique_service=True) as service:
            service._metrics_emitter_event = mock.MagicMock()
            service._metrics_emitter_event.wait.side_effect = [False, True]
            service.connector = connected_connector
            assert service._services_metric == {}
            service._send_service_status()
            service._get_metrics()
            service._update_existing_services()
            assert service._services_metric != {}

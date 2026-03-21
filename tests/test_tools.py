"""
tests/test_tools.py - Unit tests for tool modules.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ---------------------------------------------------------------------------
# tools/kubernetes_tool.py
# ---------------------------------------------------------------------------

class TestKubernetesTool:
    """Tests for KubernetesTool."""

    @pytest.mark.asyncio
    async def test_run_prepends_kubectl(self):
        """run() should prepend 'kubectl' if not already present."""
        from tools.kubernetes_tool import KubernetesTool

        tool = KubernetesTool()
        captured = []

        async def fake_shell(cmd, env_extra=None):
            captured.append(cmd)
            return {"stdout": "", "stderr": "", "returncode": 0}

        with patch("tools.kubernetes_tool._shell", side_effect=fake_shell):
            await tool.run("get pods -n default")

        assert captured[0].startswith("kubectl get pods")

    @pytest.mark.asyncio
    async def test_run_does_not_double_kubectl(self):
        """run() should not add 'kubectl' when already present."""
        from tools.kubernetes_tool import KubernetesTool

        tool = KubernetesTool()
        captured = []

        async def fake_shell(cmd, env_extra=None):
            captured.append(cmd)
            return {"stdout": "", "stderr": "", "returncode": 0}

        with patch("tools.kubernetes_tool._shell", side_effect=fake_shell):
            await tool.run("kubectl get pods")

        assert captured[0].count("kubectl") == 1

    @pytest.mark.asyncio
    async def test_get_pods(self):
        """get_pods() should call kubectl get pods with -o wide."""
        from tools.kubernetes_tool import KubernetesTool

        tool = KubernetesTool()
        with patch("tools.kubernetes_tool._shell", new=AsyncMock(return_value={"stdout": "NAME   STATUS", "stderr": "", "returncode": 0})) as mock:
            result = await tool.get_pods(namespace="kube-system")

        args = mock.call_args[0][0]
        assert "kube-system" in args
        assert "-o wide" in args

    @pytest.mark.asyncio
    async def test_get_logs(self):
        """get_logs() should include --previous flag when requested."""
        from tools.kubernetes_tool import KubernetesTool

        tool = KubernetesTool()
        with patch("tools.kubernetes_tool._shell", new=AsyncMock(return_value={"stdout": "log line", "stderr": "", "returncode": 0})) as mock:
            await tool.get_logs("my-pod", namespace="default", previous=True)

        cmd = mock.call_args[0][0]
        assert "--previous" in cmd

    @pytest.mark.asyncio
    async def test_shell_timeout_returns_error(self):
        """_shell should handle asyncio.TimeoutError gracefully."""
        import asyncio
        from tools.kubernetes_tool import _shell

        async def fake_communicate():
            raise asyncio.TimeoutError()

        mock_proc = MagicMock()
        mock_proc.communicate = fake_communicate

        with patch("asyncio.create_subprocess_shell", new=AsyncMock(return_value=mock_proc)):
            result = await _shell("sleep 100")

        assert result["returncode"] == -1
        assert "timed out" in result["stderr"].lower()


# ---------------------------------------------------------------------------
# tools/linux_tool.py
# ---------------------------------------------------------------------------

class TestLinuxTool:
    """Tests for LinuxTool."""

    @pytest.mark.asyncio
    async def test_run_delegates_to_shell(self):
        """run() should pass the command through to _shell."""
        from tools.linux_tool import LinuxTool

        tool = LinuxTool()
        with patch("tools.linux_tool._shell", new=AsyncMock(return_value={"stdout": "ok", "stderr": "", "returncode": 0})) as mock:
            await tool.run("echo hello")

        mock.assert_called_once_with("echo hello")

    @pytest.mark.asyncio
    async def test_cpu_usage(self):
        """cpu_usage() should call ps aux."""
        from tools.linux_tool import LinuxTool

        tool = LinuxTool()
        with patch("tools.linux_tool._shell", new=AsyncMock(return_value={"stdout": "data", "stderr": "", "returncode": 0})) as mock:
            await tool.cpu_usage()

        cmd = mock.call_args[0][0]
        assert "ps aux" in cmd

    @pytest.mark.asyncio
    async def test_service_status_quotes_name(self):
        """service_status() should safely quote the service name."""
        from tools.linux_tool import LinuxTool

        tool = LinuxTool()
        with patch("tools.linux_tool._shell", new=AsyncMock(return_value={"stdout": "", "stderr": "", "returncode": 0})) as mock:
            await tool.service_status("my-service")

        cmd = mock.call_args[0][0]
        assert "my-service" in cmd


# ---------------------------------------------------------------------------
# tools/cloud_tool.py
# ---------------------------------------------------------------------------

class TestCloudTool:
    """Tests for CloudTool."""

    @pytest.mark.asyncio
    async def test_run_aws(self):
        """run() should pass aws commands to _shell."""
        from tools.cloud_tool import CloudTool

        tool = CloudTool()
        with patch("tools.cloud_tool._shell", new=AsyncMock(return_value={"stdout": "cluster-list", "stderr": "", "returncode": 0})) as mock:
            await tool.run("aws eks list-clusters")

        cmd = mock.call_args[0][0]
        assert cmd.startswith("aws")

    @pytest.mark.asyncio
    async def test_run_unknown_prefix(self):
        """run() should still call _shell for unknown prefixes."""
        from tools.cloud_tool import CloudTool

        tool = CloudTool()
        with patch("tools.cloud_tool._shell", new=AsyncMock(return_value={"stdout": "", "stderr": "", "returncode": 0})) as mock:
            await tool.run("some-custom-cli --help")

        mock.assert_called_once()


# ---------------------------------------------------------------------------
# tools/ansible_tool.py
# ---------------------------------------------------------------------------

class TestAnsibleTool:
    """Tests for AnsibleTool."""

    @pytest.mark.asyncio
    async def test_run_routes_playbook(self):
        """run() should call run_playbook for .yml files."""
        from tools.ansible_tool import AnsibleTool

        tool = AnsibleTool()
        with patch.object(tool, "run_playbook", new=AsyncMock(return_value={"status": "successful"})) as mock:
            await tool.run("site.yml")

        mock.assert_called_once_with("site.yml")

    @pytest.mark.asyncio
    async def test_run_routes_shell_for_other(self):
        """run() should call _run_shell for non-.yml commands."""
        from tools.ansible_tool import AnsibleTool

        tool = AnsibleTool()
        with patch.object(tool, "_run_shell", new=AsyncMock(return_value={"status": "successful"})) as mock:
            await tool.run("ansible -m ping all")

        mock.assert_called_once()

-- Крутящийся красный блок.
-- Вставьте этот Script в ServerScriptService и нажмите Play.

local RunService = game:GetService("RunService")

local SPIN_SPEED = math.rad(90) -- градусов в секунду

local block = Instance.new("Part")
block.Name = "SpinningRedBlock"
block.Size = Vector3.new(4, 4, 4)
block.Color = Color3.fromRGB(255, 0, 0)
block.Material = Enum.Material.Neon
block.Anchored = true
block.CanCollide = true
block.CFrame = CFrame.new(0, 6, 0)
block.Parent = workspace

RunService.Heartbeat:Connect(function(dt)
	block.CFrame = block.CFrame * CFrame.Angles(0, SPIN_SPEED * dt, 0)
end)

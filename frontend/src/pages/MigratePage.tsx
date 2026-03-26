import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'

export default function MigratePage() {
  const navigate = useNavigate()
  useEffect(() => { navigate('/', { replace: true }) }, [])
  return null
}

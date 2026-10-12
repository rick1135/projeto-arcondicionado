import unittest
from unittest.mock import Mock, patch
from controller import Controller

class PlugTests(unittest.TestCase):
    def make(self):
        c = Controller({'id': 'test-air'}, plug_config={'id': 'test-plug'})
        c._device = Mock()
        c._plug_device = Mock()
        return c

    def test_power_on_orders_plug_boot_and_air(self):
        c=self.make(); events=[]
        plug=Mock(); air=Mock()
        states=iter([False,True,True])
        plug.status.side_effect=lambda: {'dps':{'1':next(states)}}
        plug.set_value.side_effect=lambda dp,v: events.append(('plug',dp,v)) or {}
        responses=iter([{'Error':'booting'},{'dps':{'1':False}},{'dps':{'1':True}}])
        air.status.side_effect=lambda: events.append(('read-air',)) or next(responses)
        air.set_value.side_effect=lambda dp,v: events.append(('air',dp,v)) or {}
        c._device.return_value=air;c._plug_device.return_value=plug
        with patch('controller.time.sleep'):
            state=c.set(1,True)
        self.assertTrue(state['1'])
        self.assertEqual(events[0],('plug',1,True))
        self.assertEqual(events[1:3],[('read-air',),('read-air',)])
        self.assertEqual(events[3],('air',1,True))

    def test_off_plug_does_not_poll_unpowered_air(self):
        c=self.make()
        c._plug_device.return_value.status.return_value={'dps':{'1':False}}
        self.assertFalse(c.status()['_ac_available'])
        c._device.assert_not_called()

    def test_power_off_keeps_plug_on(self):
        c=self.make()
        c._plug_device.return_value.status.return_value={'dps':{'1':True}}
        c._device.return_value.set_value.return_value={}
        c._device.return_value.status.return_value={'dps':{'1':False}}
        c.set(1,False)
        c._plug_device.return_value.set_value.assert_not_called()
        c._device.return_value.set_value.assert_called_once_with(1,False)

    def test_boot_timeout_never_sends_air_command_or_cuts_plug(self):
        c=self.make()
        c._plug_device.return_value.status.return_value={'dps':{'1':True}}
        c._device.return_value.status.return_value={'Error':'offline'}
        with patch('controller.time.monotonic', side_effect=[0,2]):
            with self.assertRaises(RuntimeError): c.power_on(timeout=1)
        c._device.return_value.set_value.assert_not_called()
        c._plug_device.return_value.set_value.assert_not_called()

    def test_same_device_cannot_be_used_as_air_and_plug(self):
        c=Controller({'id':'same'},plug_config={'id':'same'})
        with self.assertRaises(ValueError): c.plug_status()

    def test_unconfirmed_plug_power_prevents_air_command(self):
        c=self.make()
        c._plug_device.return_value.status.return_value={'dps':{'1':False}}
        c._plug_device.return_value.set_value.return_value={}
        with self.assertRaises(RuntimeError): c.set(1,True)
        c._device.assert_not_called()

    def test_plug_off_confirms_air_off_before_cut(self):
        c=self.make(); events=[]
        plug=c._plug_device.return_value; air=c._device.return_value
        plug.status.side_effect=[{'dps':{'1':True}}, {'dps':{'1':False}}]
        air.status.side_effect=[{'dps':{'1':True}}, {'dps':{'1':False}}]
        air.set_value.side_effect=lambda dp,v:events.append(('air',dp,v)) or {}
        plug.set_value.side_effect=lambda dp,v:events.append(('plug',dp,v)) or {}
        c.set_plug_power(False)
        self.assertEqual(events,[('air',1,False),('plug',1,False)])

    def test_explicit_plug_off_cuts_even_when_air_does_not_confirm(self):
        c=self.make(); plug=c._plug_device.return_value; air=c._device.return_value
        plug.status.side_effect=[{'dps':{'1':True}}, {'dps':{'1':False}}]
        plug.set_value.return_value={}
        air.status.return_value={'dps':{'1':True}}
        air.set_value.return_value={}
        result=c.set_plug_power(False)
        plug.set_value.assert_called_once_with(1,False)
        self.assertFalse(result['_plug_dps']['1'])
        self.assertIn('não confirmou', result['_notice'])

    def test_countdown_cancellation_does_not_change_relay(self):
        c=self.make(); plug=c._plug_device.return_value
        plug.status.return_value={'dps':{'1':False,'9':0}}
        plug.set_value.return_value={}
        c.plug_countdown(0)
        plug.set_value.assert_called_once_with(9,0)
        c._device.assert_not_called()

    def test_timer_accepts_decremented_ack(self):
        c=self.make(); plug=c._plug_device.return_value
        plug.status.side_effect=[{'dps':{'1':False,'9':0}}, {'dps':{'1':False,'9':598}}]
        plug.set_value.return_value={}
        c.plug_countdown(600)
        plug.set_value.assert_called_once_with(9,600)

    def test_air_status_discovers_new_ip_when_saved_ip_is_stale(self):
        c = Controller({'id': 'test-air', 'key': 'test-key', 'ip': '10.0.0.5'})
        stale = Mock()
        stale.status.return_value = {'Error': 'unreachable'}
        discovered = Mock()
        discovered.status.return_value = {'dps': {'1': False, '2': 22}}
        discovered.address = '10.0.0.17'
        def device(config):
            return discovered if config['ip'] == 'Auto' else stale
        c._make_device = Mock(side_effect=device)
        status = c.status()
        self.assertFalse(status['1'])
        self.assertEqual(c.config['ip'], '10.0.0.17')
        self.assertEqual(c._make_device.call_count, 2)
